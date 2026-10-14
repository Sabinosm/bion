"""
Schemas Pydantic de ENTRADA para medicamento em uso (Bloco 2).

Operações (sem atualização no lugar -- ver model):
- Create: registra um medicamento ATIVO. Identifica o catálogo por
  `uuid_catalogo` (nunca pelo id interno). Sem uuid_catalogo, a
  `descricao` é obrigatória; com uuid_catalogo, se vier vazia o service
  preenche com o princípio ativo do catálogo.
- Encerrar: fecha o registro como 'interrompido' ou 'concluido'.
- Substituir: troca dose/frequência/descrição = fecha o antigo e cria o
  novo (feito no service, atomicamente).
- Remover: soft delete com motivo (mesmo padrão dos demais domínios).

Checagens que dependem do banco (uuid_catalogo existe, registro ativo,
datas contra `desde`) ficam no service, não aqui.
"""

import uuid as _uuid
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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


def _data_nao_futura(v: Optional[date]) -> Optional[date]:
    if v is not None and v > date.today():
        raise ValueError("não pode ser uma data futura")
    return v


class MedicamentoEmUsoCreateSchema(BaseModel):
    uuid_catalogo: Optional[str] = None
    descricao: Optional[str] = Field(default=None, max_length=2000, validate_default=True)
    dose: Optional[str] = Field(default=None, max_length=100)
    frequencia: Optional[str] = Field(default=None, max_length=100)
    desde: Optional[date] = None

    @field_validator("uuid_catalogo")
    @classmethod
    def _uuid_valido(cls, v: Optional[str]) -> Optional[str]:
        v = _strip_ou_none(v)
        if v is None:
            return None
        try:
            return str(_uuid.UUID(v))
        except ValueError:
            raise ValueError("uuid inválido")

    @field_validator("descricao")
    @classmethod
    def _descricao(cls, v: Optional[str], info) -> Optional[str]:
        v = _strip_ou_none(v)
        if v is None and not info.data.get("uuid_catalogo"):
            raise ValueError(
                "obrigatória quando o medicamento não está vinculado ao catálogo"
            )
        return v

    @field_validator("dose", "frequencia")
    @classmethod
    def _normalizado(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("desde")
    @classmethod
    def _desde_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        return _data_nao_futura(v)


class MedicamentoEmUsoEncerrarSchema(BaseModel):
    """Fecha um registro ativo. `ate` omitido = hoje."""
    status_uso: Literal["interrompido", "concluido"]
    ate: Optional[date] = None

    @field_validator("ate")
    @classmethod
    def _ate_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        return _data_nao_futura(v)


class MedicamentoEmUsoSubstituirSchema(BaseModel):
    """Troca de dose/frequência/descrição: pelo menos um dos três deve
    vir. `data_mudanca` omitida = hoje (vira `ate` do antigo e `desde` do
    novo). Quem não vier é copiado do registro antigo."""
    descricao: Optional[str] = Field(default=None, max_length=2000)
    dose: Optional[str] = Field(default=None, max_length=100)
    frequencia: Optional[str] = Field(default=None, max_length=100)
    data_mudanca: Optional[date] = None

    @field_validator("descricao")
    @classmethod
    def _descricao(cls, v: Optional[str]) -> str:
        if v is None:
            raise ValueError("não pode ser nulo")
        return _validar_texto_obrigatorio(v)

    @field_validator("dose", "frequencia")
    @classmethod
    def _normalizado(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("data_mudanca")
    @classmethod
    def _data_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        return _data_nao_futura(v)

    @model_validator(mode="after")
    def _algum_campo(self) -> "MedicamentoEmUsoSubstituirSchema":
        if not ({"descricao", "dose", "frequencia"} & self.model_fields_set):
            raise ValueError("informe ao menos um de: descricao, dose, frequencia")
        return self

    def campos_informados(self) -> dict:
        return {
            c: getattr(self, c)
            for c in ("descricao", "dose", "frequencia")
            if c in self.model_fields_set
        }


class MedicamentoEmUsoRemoverSchema(BaseModel):
    """Soft delete (DELETE). motivo é obrigatório; motivo_delete='outro'
    exige observacoes_delete preenchida."""
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
    def _outro_exige_observacao(self) -> "MedicamentoEmUsoRemoverSchema":
        if self.motivo_delete == "outro" and not self.observacoes_delete:
            raise ValueError(
                "observacoes_delete é obrigatória e não pode ser vazia "
                "quando motivo_delete='outro'"
            )
        return self
