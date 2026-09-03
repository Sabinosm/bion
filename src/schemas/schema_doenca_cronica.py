"""
Schema Pydantic de ENTRADA para doença crônica.

O Literal de `status` é cópia manual do db.Enum de DoencaCronica --
não há introspecção automática do schema do banco aqui. Se o Enum do
model mudar, este arquivo precisa ser atualizado junto. O mesmo vale
para o Literal de `motivo_delete` em DoencaCronicaRemoverSchema, cópia
manual do db.Enum `motivo_delete` do model.

ALTERADO: validação reforçada --
- codigo_cid10 agora valida o FORMATO CID-10 (letra + 2 dígitos +
  opcional ".dígito(s)"), além do tamanho -- pega erro de digitação
  óbvio sem depender de uma tabela CID completa.
- descricao_cid10/observacoes ganharam strip + rejeição de string
  vazia/só-espaços (mesmo padrão de substancia em AlergiaCreateSchema).
- desde não pode ser uma data futura (não existe "doença crônica desde
  o ano que vem").
"""

import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# Formato CID-10: uma letra (categoria) + dois dígitos + opcionalmente
# ".x" ou ".xx" (subcategoria). Ex.: E11, E11.9, J45.0. Case-insensitive
# na entrada, normalizado para maiúsculo.
_REGEX_CID10 = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")


def _formatar_erros_pydantic(exc: ValidationError) -> str:
    """Transforma a lista de erros do Pydantic numa mensagem curta,
    uma linha por campo -- consistente com o formato que
    DadosInvalidosError já usava ('Campos obrigatórios ausentes: x, y').
    """
    partes = []
    for erro in exc.errors():
        campo = ".".join(str(p) for p in erro["loc"]) or "(corpo)"
        partes.append(f"{campo}: {erro['msg']}")
    return "; ".join(partes)


def _validar_formato_cid10(v: str) -> str:
    v = v.strip().upper()
    if not v:
        raise ValueError("não pode ser vazio ou só espaços")
    if not _REGEX_CID10.match(v):
        raise ValueError(
            "formato inválido para CID-10 (esperado ex.: 'E11' ou 'E11.9')"
        )
    return v


def _validar_texto_obrigatorio(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("não pode ser vazio ou só espaços")
    return v


def _strip_ou_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    return v or None


class DoencaCronicaCreateSchema(BaseModel):
    codigo_cid10: str = Field(min_length=1, max_length=10)
    descricao_cid10: str = Field(min_length=1, max_length=255)
    desde: date
    status: Literal["ativa", "em-remissao"]
    observacoes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("codigo_cid10")
    @classmethod
    def _codigo_cid10_valido(cls, v: str) -> str:
        return _validar_formato_cid10(v)

    @field_validator("descricao_cid10")
    @classmethod
    def _descricao_cid10_sem_espacos_vazios(cls, v: str) -> str:
        return _validar_texto_obrigatorio(v)

    @field_validator("observacoes")
    @classmethod
    def _observacoes_normalizadas(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("desde")
    @classmethod
    def _desde_nao_futura(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("não pode ser uma data futura")
        return v


class DoencaCronicaAtualizarSchema(BaseModel):
    """NOVO: atualização parcial (PATCH-like) -- todo campo é opcional,
    só o que vier é validado e aplicado. codigo_cid10/descricao_cid10
    incluídos como editáveis: diferente de tipo sanguíneo (que separa
    'novo exame' de 'corrigir'), doença crônica não tem um conceito de
    'nova ocorrência' -- é o mesmo registro sendo corrigido/atualizado
    (ex: mudar status de 'ativa' para 'em-remissao' com o tempo, ou
    corrigir um CID digitado errado).
    """
    codigo_cid10: Optional[str] = Field(default=None, min_length=1, max_length=10)
    descricao_cid10: Optional[str] = Field(default=None, min_length=1, max_length=255)
    desde: Optional[date] = None
    status: Optional[Literal["ativa", "em-remissao"]] = None
    observacoes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("codigo_cid10")
    @classmethod
    def _codigo_cid10_valido(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validar_formato_cid10(v)

    @field_validator("descricao_cid10")
    @classmethod
    def _descricao_cid10_sem_espacos_vazios(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validar_texto_obrigatorio(v)

    @field_validator("observacoes")
    @classmethod
    def _observacoes_normalizadas(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("desde")
    @classmethod
    def _desde_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("não pode ser uma data futura")
        return v

    def campos_informados(self) -> dict:
        return self.model_dump(exclude_unset=True)


class DoencaCronicaRemoverSchema(BaseModel):
    """NOVO: schema de entrada para o soft delete (DELETE) -- motivo é
    obrigatório, exige explicitação de por que a doença crônica está
    sendo removida (auditoria/LGPD).

    ALTERADO: motivo_delete='outro' agora exige `observacoes_delete`
    preenchida (não vazia/só-espaços) -- 'outro' sem nenhum detalhe é
    inútil pra quem for auditar depois; os outros motivos já são
    autoexplicativos pelo próprio Enum e não exigem observação, mas
    aceitam se vier."""
    motivo_delete: Literal[
        "erro-digitacao",
        "registro-duplicado",
        "diagnostico-incorreto",
        "solicitacao-paciente",
        "outro",
    ]
    observacoes_delete: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("observacoes_delete")
    @classmethod
    def _observacoes_delete_normalizadas(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @model_validator(mode="after")
    def _outro_exige_observacao(self) -> "DoencaCronicaRemoverSchema":
        if self.motivo_delete == "outro" and not self.observacoes_delete:
            raise ValueError(
                "observacoes_delete é obrigatória e não pode ser vazia "
                "quando motivo_delete='outro'"
            )
        return self