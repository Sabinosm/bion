"""
Schemas Pydantic (v2) para o fluxo de assinatura digital LGPD.
Colocar em src/domains/paciente/schemas/ (junto de schema_consentimento.py).

Responsabilidade dos schemas: FORMATO (tipos, tamanhos, hex, PNG base64).
Regras que dependem de estado ficam no service: hash == o da sessão,
token válido/não expirado, versão do termo existente (template).
"""

import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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
    # Gate do recurso de IA: o código da IA só roda se este escopo estiver no
    # consentimento ativo (ConsentimentoService.escopo_permitido). Prontuário e
    # protocolos clínicos NÃO dependem dele.
    "apoio_ia": "Uso dos meus dados clínicos (sem nome, CPF ou contato) em recurso de apoio por inteligência artificial no meu atendimento",
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


# versão vira nome de arquivo do template: só caracteres seguros (sem '/', '\\' ou '..' no início)
_REGEX_VERSAO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")


class GerarLinkAssinaturaSchema(BaseModel):
    """Só a versão vem do cliente. Texto, PDF e unidade (= empresa da sessão)
    são resolvidos no servidor (ver termo_renderer.gerar_termo)."""
    versao_termo: str = Field(min_length=1, max_length=50)

    @field_validator("versao_termo")
    @classmethod
    def _versao_valida(cls, v: str) -> str:
        v = v.strip()
        if not _REGEX_VERSAO.match(v):
            raise ValueError("versão inválida (use letras, números, ponto, hífen e sublinhado)")
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
    escopo: List[str] = Field(default_factory=list, max_length=20)          # ACEITOS
    # OFERECIDOS = tudo que o termo mostrou na tela. Recusados = oferecidos - aceitos.
    # Necessário porque o catálogo cresce (só adiciona): sem isso, um escopo criado
    # depois da assinatura pareceria "recusado". Registros antigos não têm: ficam [].
    escopos_oferecidos: List[str] = Field(default_factory=list, max_length=20)
    audit: AuditoriaAssinaturaSchema

    @field_validator("escopo", "escopos_oferecidos")
    @classmethod
    def _escopos(cls, v: List[str]) -> List[str]:
        return _validar_escopos(v)

    @model_validator(mode="after")
    def _aceitos_dentro_dos_oferecidos(self):
        # não dá para aceitar o que não foi oferecido (quando se sabe o que foi oferecido)
        if self.escopos_oferecidos and not set(self.escopo) <= set(self.escopos_oferecidos):
            raise ValueError("escopo contém item que não consta em escopos_oferecidos")
        return self


class ConsentimentoDigitalCreateSchema(BaseModel):
    versao_termo: str = Field(min_length=1, max_length=50)
    canal_coleta: Literal["presencial-digital"] = "presencial-digital"
    hash_documento: str                      # obrigatório aqui (opcional no manual)
    escopo_consentimento: EscopoDigitalSchema

    @field_validator("hash_documento")
    @classmethod
    def _hash(cls, v: str) -> str:
        return _validar_sha256(v)