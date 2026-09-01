"""
Schema Pydantic de ENTRADA para medicamento em uso.

O Literal de `status_uso` é cópia manual do db.Enum de
MedicamentoEmUso -- não há introspecção automática do schema do banco
aqui. Se o Enum do model mudar, este arquivo precisa ser atualizado
junto.

Checagem de que id_catalogo EXISTE em catalogo_medicamentos não entra
aqui -- é uma FK, não formato, então fica no service (query real
contra o banco), não no schema.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator


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


class MedicamentoEmUsoCreateSchema(BaseModel):
    id_catalogo: int = Field(gt=0)
    descricao: str = Field(min_length=1)
    dose: Optional[str] = Field(default=None, max_length=100)
    frequencia: Optional[str] = Field(default=None, max_length=100)
    desde: Optional[date] = None
    flag_em_uso: bool = True
    status_uso: Optional[Literal["ativo", "interrompido", "concluido"]] = None

    @field_validator("status_uso")
    @classmethod
    def _default_conforme_flag(cls, v, info):
        # Reproduz a regra que já existia no service: se status_uso não
        # vier, deriva de flag_em_uso -- mantido aqui para não perder
        # esse comportamento ao migrar a validação pro schema.
        if v is not None:
            return v
        flag = info.data.get("flag_em_uso", True)
        return "ativo" if flag else "interrompido"