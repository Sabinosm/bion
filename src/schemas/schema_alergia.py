"""
Schema Pydantic de ENTRADA para alergia e reação alérgica.

Cobre os dois juntos porque adicionar_alergia() cria a alergia E a
primeira reação na mesma chamada (ver Alergia.registrar_reacao) --
mesmo agrupamento que já existia no código antes da divisão.

Os Literal abaixo são cópia manual dos db.Enum de Alergia/ReacaoAlergia
-- não há introspecção automática do schema do banco aqui. Se o Enum
do model mudar, este arquivo precisa ser atualizado junto.
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


class AlergiaCreateSchema(BaseModel):
    substancia: str = Field(min_length=1, max_length=255)
    codigo_substancia: Optional[str] = Field(default=None, max_length=100)
    flag_confirmado: bool = False
    # Campos que viram a PRIMEIRA ReacaoAlergia (ver Alergia.registrar_reacao)
    tipo_reacao: Literal["cutanea", "respiratoria", "anafilaxia",
                          "gastrointestinal", "cardiovascular", "sistemica"]
    gravidade: Literal["leve", "moderada", "grave"]
    descricao_reacao: Optional[str] = None

    @field_validator("substancia")
    @classmethod
    def _substancia_sem_espacos_vazios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("não pode ser vazio ou só espaços")
        return v


class ReacaoAlergiaCreateSchema(BaseModel):
    manifestacao: Literal["cutanea", "respiratoria", "anafilaxia",
                           "gastrointestinal", "cardiovascular", "sistemica"]
    gravidade: Literal["leve", "moderada", "grave"]
    descricao: Optional[str] = None
    data_ocorrencia: Optional[date] = None