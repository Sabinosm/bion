"""
Schemas Pydantic (v2) para o fluxo de assinatura digital LGPD.
Colocar em src/domains/paciente/schemas/ (junto de schema_consentimento.py).

Responsabilidade dos schemas: FORMATO (tipos, tamanhos, hex, PNG base64).
Regras que dependem de estado ficam no service: hash == o da sessão,
PDF dentro de CONSENT_PDF_TERMOS, token válido/não expirado.
"""

import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

_REGEX_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
_PREFIXO_PNG = "data:image/png;base64,"

# Catálogo de escopos = FINALIDADES ESPECÍFICAS (LGPD art. 8 §4 e art. 11, I).
# Tratamento para cuidado em saúde NÃO é escopo: tem base legal própria
# (art. 11, II, "f"). Aqui só entra o que é opcional e exige consentimento.
# PONTO DE PARTIDA -- valide a lista e os textos com o jurídico/DPO.
# A chave (código) é gravada no banco: não renomeie depois, só adicione.
ESCOPOS_VALIDOS = {
    "marketing": "Receber comunicações promocionais e ofertas",
    "comunicacao": "Contato por e-mail, SMS ou WhatsApp sobre meu atendimento",
    "compartilhamento": "Compartilhar meus dados com parceiros (ex.: laboratórios, convênios) além do necessário ao atendimento",
    "pesquisa": "Uso dos meus dados, de forma anonimizada quando possível, em pesquisa científica",
    "uso_imagem": "Uso de imagens (ex.: fotos de lesões ou exames) para fins didáticos",
}


def _validar_escopos(v: List[str]) -> List[str]:
    limpos = list(dict.fromkeys(e.strip() for e in v))   # sem duplicados, mantém ordem
    invalidos = [e for e in limpos if e not in ESCOPOS_VALIDOS]
    if invalidos:
        raise ValueError(f"escopo(s) desconhecido(s): {', '.join(invalidos)}")
    return limpos


def _validar_sha256(v: str) -> str:
    v = v.strip()
    if not _REGEX_SHA256_HEX.match(v):
        raise ValueError("esperado SHA-256 em hexadecimal (64 caracteres)")
    return v.lower()


class GerarLinkAssinaturaSchema(BaseModel):
    id_unidade: int = Field(gt=0)
    versao_termo: str = Field(min_length=1, max_length=50)
    pdf_termo_path: str = Field(min_length=1, max_length=500)   # coluna é String(500)
    texto_termo: str = Field(min_length=10, max_length=200_000)

    # ATENÇÃO: sem validação de os.path.isfile aqui (a versão anterior tinha).
    # Checar existência de caminho vindo do cliente permite sondar o servidor
    # (200 vs 422 revela quais arquivos existem) e não restringe o diretório.
    # Quem valida é ConsentimentoDigitalService._resolver_pdf_termo.

    @field_validator("versao_termo", "pdf_termo_path", "texto_termo")
    @classmethod
    def _sem_espacos_vazios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("não pode ser vazio ou só espaços")
        return v


class AssinaturaDigitalSchema(BaseModel):
    confirmo_identidade: bool
    declaro_consentimento: bool
    # ~1 MB de PNG em base64 + prefixo. O service ainda confere magic bytes
    # e tamanho decodificado.
    assinatura_canvas: str = Field(min_length=100, max_length=1_500_000)
    hash_pdf_original: str
    # user_agent agora é opcional: o service prefere o header do servidor
    # (o do front pode ser forjado).
    user_agent: Optional[str] = Field(default=None, max_length=500)
    geolocalizacao: Optional[str] = Field(default=None, max_length=200)  # coluna String(200)
    geo_divergente: bool = False
    escopos_selecionados: List[str] = Field(default_factory=list, max_length=20)

    @field_validator("confirmo_identidade", "declaro_consentimento")
    @classmethod
    def _checkbox_marcado(cls, v: bool) -> bool:
        if not v:
            raise ValueError("este campo deve ser marcado")
        return v

    @field_validator("assinatura_canvas")
    @classmethod
    def _deve_ser_png_base64(cls, v: str) -> str:
        if not v.startswith(_PREFIXO_PNG):
            raise ValueError(f"deve ser PNG em base64 com prefixo {_PREFIXO_PNG}")
        return v

    @field_validator("hash_pdf_original")
    @classmethod
    def _hash_sha256(cls, v: str) -> str:
        return _validar_sha256(v)

    @field_validator("escopos_selecionados")
    @classmethod
    def _escopos_validos(cls, v: List[str]) -> List[str]:
        return _validar_escopos(v)


# ============================================================================
# Registro do CONSENTIMENTO criado pelo fluxo digital (saída do service,
# entrada do ConsentimentoService.ativar_novo). Garante que todo consentimento
# 'presencial-digital' tenha hash e trilha de auditoria no formato esperado --
# o que o registro manual não consegue garantir.
# ============================================================================

class AuditoriaAssinaturaSchema(BaseModel):
    id_sessao: int
    ip: Optional[str] = Field(default=None, max_length=45)          # coluna String(45)
    user_agent: Optional[str] = Field(default=None, max_length=500)
    geolocalizacao: Optional[str] = Field(default=None, max_length=200)
    geo_divergente: bool = False
    texto_integral_aceito: str = Field(min_length=1)
    hash_pdf_original: str
    hash_pdf_final: str
    checkboxes: Dict[str, bool] = Field(
        default_factory=lambda: {"confirmo_identidade": True, "declaro_consentimento": True}
    )

    @field_validator("hash_pdf_original", "hash_pdf_final")
    @classmethod
    def _hashes(cls, v: str) -> str:
        return _validar_sha256(v)


class EscopoDigitalSchema(BaseModel):
    """Formato gravado em consentimento_lgpd.escopo_consentimento_json."""
    escopo: List[str] = Field(default_factory=list, max_length=20)
    audit: AuditoriaAssinaturaSchema

    @field_validator("escopo")
    @classmethod
    def _escopos(cls, v: List[str]) -> List[str]:
        return _validar_escopos(v)


class ConsentimentoDigitalCreateSchema(BaseModel):
    versao_termo: str = Field(min_length=1, max_length=50)
    canal_coleta: Literal["presencial-digital"] = "presencial-digital"
    hash_documento: str                      # obrigatório aqui (opcional no manual)
    escopo_consentimento: EscopoDigitalSchema

    @field_validator("hash_documento")
    @classmethod
    def _hash(cls, v: str) -> str:
        return _validar_sha256(v)