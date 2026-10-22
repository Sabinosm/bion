"""
schema_empresa_protocolo.py

Schemas Pydantic de ENTRADA da liberação institucional de protocolos: um para
liberar/bloquear um protocolo e escolher sua política, outro para definir o
padrão institucional de um escopo. Validam os valores aceitos e rejeitam
qualquer campo não previsto. Dados de governança, como quem aprovou e quando,
nunca fazem parte do payload: vêm da sessão e são preenchidos pelo service,
para que o cliente não possa forjá-los.
"""

from typing import Optional

from pydantic import BaseModel, field_validator


ESCOPOS_VALIDOS = {"triagem", "consulta", "ambos"}
POLITICAS_VALIDAS = {"obrigatorio", "opcional"}


class AlterarStatusEmpresaProtocoloSchema(BaseModel):
    """Liberar/bloquear um protocolo. `politica` None = não altera a atual."""

    ativo: bool
    politica: Optional[str] = None

    model_config = {
        "extra": "forbid",
    }

    @field_validator("politica")
    @classmethod
    def valida_politica(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in POLITICAS_VALIDAS:
            raise ValueError(f"politica inválida: '{v}'. Valores aceitos: {sorted(POLITICAS_VALIDAS)}.")
        return v


class DefinirDefaultInstitucionalSchema(BaseModel):
    """Escopo para o qual o protocolo será o padrão institucional."""

    escopo: str

    model_config = {
        "extra": "forbid",
    }

    @field_validator("escopo")
    @classmethod
    def valida_escopo(cls, v: str) -> str:
        if v not in ESCOPOS_VALIDOS:
            raise ValueError(f"escopo inválido: '{v}'. Valores aceitos: {sorted(ESCOPOS_VALIDOS)}.")
        return v