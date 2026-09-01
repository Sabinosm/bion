"""
Schema Pydantic de ENTRADA para doença crônica.

O Literal de `status` é cópia manual do db.Enum de DoencaCronica --
não há introspecção automática do schema do banco aqui. Se o Enum do
model mudar, este arquivo precisa ser atualizado junto.
"""

from datetime import date
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


class DoencaCronicaCreateSchema(BaseModel):
    codigo_cid10: str = Field(min_length=1, max_length=10)
    descricao_cid10: str = Field(min_length=1, max_length=255)
    desde: date
    status: Literal["ativa", "em-remissao"]
    observacoes: Optional[str] = None