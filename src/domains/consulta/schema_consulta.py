"""
Schema Pydantic de ENTRADA para Consulta (abrir, encerrar, evadir).

Os Literal abaixo são a ÚNICA cópia manual dos db.Enum de Consulta
(origem_encaminhamento e desfecho_final) -- não há introspecção
automática do schema do banco. Se o Enum do model mudar, atualize aqui;
ConsultaService importa DESFECHOS_VALIDOS / ORIGENS_VALIDAS deste
arquivo, então não existe uma segunda lista para esquecer.

Validações principais: ConsultaAbrirSchema exige EXATAMENTE UMA das três
formas de abertura (uuid_paciente | paciente | paciente_nao_identificado),
exige motivo_emergencia no caso de paciente não identificado e rejeita
campos de emergência misturados com as outras formas; uuid_paciente deve
ser um UUID válido; texto livre é normalizado (só espaços vira None).

O conteúdo de `paciente` (dados de cadastro) NÃO é validado aqui: isso é
responsabilidade do schema/serviço de Paciente. Aqui só garantimos que é
um objeto não vazio.
"""

import uuid as _uuid
from typing import Literal, Optional, get_args
from src.core.erros_pydantic import erros_pydantic_por_campo
from pydantic import (
    BaseModel, Field, StrictBool, field_validator, model_validator,
)

_ORIGENS = Literal["espontanea", "SAMU", "transferencia", "regulacao"]
_DESFECHOS = Literal["alta", "internacao", "transferencia", "obito", "evasao"]
_SEXOS = Literal["M", "F", "I"]

ORIGENS_VALIDAS = get_args(_ORIGENS)
DESFECHOS_VALIDOS = get_args(_DESFECHOS)


def _strip_ou_none(v: Optional[str]) -> Optional[str]:
    """String só com espaços vira None; com conteúdo, volta sem espaços
    nas pontas."""
    if v is None:
        return None
    v = v.strip()
    return v or None


class ConsultaAbrirSchema(BaseModel):
    """Corpo de POST /consultas/ (ver ConsultaService.abrir).

    Formas aceitas (exatamente uma):
      {"uuid_paciente": "..."}
      {"paciente": {...}}
      {"paciente_nao_identificado": true, "motivo_emergencia": "...",
       "sexo_biologico": "M|F|I"}
    """
    uuid_paciente: Optional[str] = None
    paciente: Optional[dict] = None
    # StrictBool: "true" (string) NÃO vale, igual ao `is True` do service.
    paciente_nao_identificado: StrictBool = False
    motivo_emergencia: Optional[str] = Field(default=None, max_length=2000)
    sexo_biologico: _SEXOS = "I"
    origem_encaminhamento: _ORIGENS = "espontanea"

    @field_validator("uuid_paciente")
    @classmethod
    def _uuid_paciente_valido(cls, v: Optional[str]) -> Optional[str]:
        v = _strip_ou_none(v)
        if v is None:
            return None
        try:
            _uuid.UUID(v)
        except ValueError:
            raise ValueError("não é um UUID válido")
        return v

    @field_validator("motivo_emergencia")
    @classmethod
    def _motivo_normalizado(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @model_validator(mode="after")
    def _exatamente_uma_forma(self) -> "ConsultaAbrirSchema":
        formas = (bool(self.uuid_paciente), bool(self.paciente),
                  self.paciente_nao_identificado)
        if sum(formas) != 1:
            raise ValueError(
                "informe exatamente um de: uuid_paciente, paciente, "
                "paciente_nao_identificado"
            )

        if self.paciente_nao_identificado:
            if not self.motivo_emergencia:
                raise ValueError(
                    "motivo_emergencia é obrigatório quando "
                    "paciente_nao_identificado=true"
                )
        else:
            if self.motivo_emergencia:
                raise ValueError(
                    "motivo_emergencia só é aceito com "
                    "paciente_nao_identificado=true"
                )
            if "sexo_biologico" in self.model_fields_set:
                raise ValueError(
                    "sexo_biologico só é aceito com "
                    "paciente_nao_identificado=true"
                )
        return self


class ConsultaEncerrarSchema(BaseModel):
    """Corpo de POST /consultas/<uuid>/encerrar. desfecho_final é
    obrigatório. justificativa vai só para a trilha de auditoria."""
    desfecho_final: _DESFECHOS
    justificativa: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("justificativa")
    @classmethod
    def _justificativa_normalizada(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)


class ConsultaEvadirSchema(BaseModel):
    """Corpo de POST /consultas/<uuid>/evadir. O desfecho é fixo
    ('evasao'), então só existe a justificativa (opcional, auditoria)."""
    justificativa: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("justificativa")
    @classmethod
    def _justificativa_normalizada(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)