"""
Schema Pydantic de ENTRADA para consentimento LGPD.

O Literal de `canal_coleta` é cópia manual do db.Enum de Consentimento
-- não há introspecção automática do schema do banco aqui. Se o Enum
do model mudar, este arquivo precisa ser atualizado junto.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError


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


class ConsentimentoCreateSchema(BaseModel):
    versao_termo: str = Field(min_length=1, max_length=50)
    canal_coleta: Literal["presencial-papel", "presencial-digital", "portal-online", "totem"]
    escopo_consentimento: Optional[dict] = None
    hash_documento: Optional[str] = Field(default=None, max_length=64)


class ConsentimentoDispensaEmergenciaSchema(BaseModel):
    """NOVO: entrada para dispensar consentimento por urgência/
    emergência -- fluxo separado de ConsentimentoCreateSchema porque
    os campos exigidos são outros (motivo é obrigatório aqui; não
    exige canal_coleta/versao_termo, já que não houve coleta de fato)."""
    motivo: str = Field(min_length=1, max_length=1000)


class ConsentimentoRevogarSchema(BaseModel):
    """NOVO: motivo passou a ser obrigatório -- antes revogar() aceitava
    motivo=None e caía num fallback genérico ("Revogado a pedido do
    titular."), inconsistente com dispensar_por_emergencia, que já
    exige motivo. Revogação também é um evento que merece ficar
    registrado com uma razão de verdade, não um texto padrão."""
    motivo: str = Field(min_length=1, max_length=1000)