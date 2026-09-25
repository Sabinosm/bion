"""Schema Pydantic de ENTRADA para EmpresaProtocolo (liberação institucional).

Separação por sensibilidade, no mesmo espírito de AtualizacaoEmpresaSchema:
- alterar 'ativo' e 'politica' é ação de governança clínica, sempre exige
  quem aprovou (aprovado_por vem da sessão, nunca do payload do cliente).
- escopo_default_institucional é uma ação derivada, tratada em método
  próprio do Service (não faz parte deste schema de toggle simples).
"""

from typing import Optional

from pydantic import BaseModel, field_validator


ESCOPOS_VALIDOS = {"triagem", "consulta", "ambos"}
POLITICAS_VALIDAS = {"obrigatorio", "opcional"}


class AlterarStatusEmpresaProtocoloSchema(BaseModel):
    ativo: bool
    politica: Optional[str] = None  # None = não altera a política atual

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