"""
Schema Pydantic de ENTRADA para doença crônica.

Os Literal de `status` e `motivo_delete` são cópia manual dos db.Enum do
model -- se o Enum mudar, este arquivo precisa mudar junto.

codigo_cid10 valida o FORMATO CID-10 (letra + 2 dígitos + opcional
".dígito(s)"). descricao_cid10/observacoes rejeitam vazio/só-espaços.
desde não pode ser data futura.

BLOCO 2 -- quatro schemas de entrada:
  - Create:    nova doença (nasce vigente).
  - Atualizar: SÓ `observacoes` (texto livre, sem significado clínico
               que exija histórico). Qualquer outro campo é recusado com
               a orientação de usar /revisar.
  - Revisar:   muda status/CID/desde (e opcionalmente observacoes). O
               service FECHA a linha vigente e cria uma nova (fechar +
               criar novo). Exige ao menos uma mudança clínica; CID e
               descrição andam juntos.
  - Remover:   soft delete com motivo.
"""

import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from src.core.erros_pydantic import erros_pydantic_por_campo

# Formato CID-10: uma letra + dois dígitos + opcionalmente ".x" ou ".xx".
_REGEX_CID10 = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")

_STATUS = Literal["ativa", "em-remissao"]
_CAMPOS_CLINICOS = ("codigo_cid10", "descricao_cid10", "desde", "status")


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


def _validar_data_nao_futura(v: Optional[date]) -> Optional[date]:
    if v is not None and v > date.today():
        raise ValueError("não pode ser uma data futura")
    return v


class DoencaCronicaCreateSchema(BaseModel):
    codigo_cid10: str = Field(min_length=1, max_length=10)
    descricao_cid10: str = Field(min_length=1, max_length=255)
    desde: date
    status: _STATUS
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
        return _validar_data_nao_futura(v)


class DoencaCronicaAtualizarSchema(BaseModel):
    """Correção de TEXTO: só `observacoes` pode mudar no lugar.

    status, CID e desde são fatos clínicos com histórico: mudam por
    POST .../<uuid>/revisar (fecha a linha vigente e cria uma nova).
    Enviar qualquer um deles aqui devolve 422 com essa orientação.
    `observacoes: null` limpa o texto; omitir o campo é erro (corpo vazio
    não é uma atualização).
    """
    model_config = ConfigDict(extra="forbid")

    observacoes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def _campos_clinicos_vao_para_revisar(cls, data):
        if isinstance(data, dict):
            enviados = [c for c in _CAMPOS_CLINICOS if c in data]
            if enviados:
                raise ValueError(
                    f"{', '.join(enviados)} não podem ser editados no lugar; "
                    "use a rota de revisão (/revisar), que preserva o histórico"
                )
        return data

    @field_validator("observacoes")
    @classmethod
    def _observacoes_normalizadas(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @model_validator(mode="after")
    def _exige_observacoes(self) -> "DoencaCronicaAtualizarSchema":
        if "observacoes" not in self.model_fields_set:
            raise ValueError("informe 'observacoes'")
        return self

    def campos_informados(self) -> dict:
        return self.model_dump(exclude_unset=True)


class DoencaCronicaRevisarSchema(BaseModel):
    """Revisão clínica: o que vier preenchido substitui o valor vigente na
    LINHA NOVA; o que não vier é copiado da vigente. Regras:
      - ao menos um de codigo_cid10/descricao_cid10/desde/status;
      - codigo_cid10 e descricao_cid10 sempre juntos (corrigir o CID
        corrige a descrição que o acompanha);
      - `observacoes` é opcional (omitida = copia; null = limpa).
    Se nada realmente mudar em relação à vigente, o service devolve 422.
    """
    model_config = ConfigDict(extra="forbid")

    codigo_cid10: Optional[str] = Field(default=None, min_length=1, max_length=10)
    descricao_cid10: Optional[str] = Field(default=None, min_length=1, max_length=255)
    desde: Optional[date] = None
    status: Optional[_STATUS] = None
    observacoes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("codigo_cid10")
    @classmethod
    def _codigo_cid10_valido(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _validar_formato_cid10(v)

    @field_validator("descricao_cid10")
    @classmethod
    def _descricao_cid10_sem_espacos_vazios(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _validar_texto_obrigatorio(v)

    @field_validator("observacoes")
    @classmethod
    def _observacoes_normalizadas(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("desde")
    @classmethod
    def _desde_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        return _validar_data_nao_futura(v)

    @model_validator(mode="after")
    def _cid_e_descricao_juntos(self) -> "DoencaCronicaRevisarSchema":
        if (self.codigo_cid10 is None) != (self.descricao_cid10 is None):
            raise ValueError("codigo_cid10 e descricao_cid10 devem ser informados juntos")
        return self

    @model_validator(mode="after")
    def _alguma_mudanca_clinica(self) -> "DoencaCronicaRevisarSchema":
        if all(getattr(self, c) is None for c in _CAMPOS_CLINICOS):
            raise ValueError(
                "informe ao menos um de: codigo_cid10 (com descricao_cid10), desde, status"
            )
        return self

    def campos_informados(self) -> dict:
        """Campos clínicos não nulos + observacoes se veio no corpo (mesmo null)."""
        dados = {c: getattr(self, c) for c in _CAMPOS_CLINICOS if getattr(self, c) is not None}
        if "observacoes" in self.model_fields_set:
            dados["observacoes"] = self.observacoes
        return dados


class DoencaCronicaRemoverSchema(BaseModel):
    """Soft delete: motivo obrigatório; motivo_delete='outro' exige
    observacoes_delete preenchida (não vazia/só-espaços)."""
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