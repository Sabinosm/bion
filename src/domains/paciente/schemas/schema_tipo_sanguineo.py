"""
Schema Pydantic de ENTRADA para observação de tipo sanguíneo.

O Literal é cópia manual do db.Enum de ObservacaoTipoSanguineo -- não
há introspecção automática do schema do banco aqui. Se o Enum do
model mudar, este arquivo precisa ser atualizado junto.

Normaliza caixa antes de validar contra o Literal: "a+", "A+" e " A+ "
são todos aceitos e normalizados para "A+".
"""

from typing import Literal
from src.core.erros_pydantic import erros_pydantic_por_campo
from pydantic import BaseModel, ValidationError, field_validator

_TIPOS_VALIDOS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "DESCONHECIDO"}
# "desconhecido" é o único valor do Enum que não é sigla de tipo
# sanguíneo -- mapeado à parte para manter a grafia minúscula original
# depois de normalizar a entrada.
_MAPA_NORMALIZACAO = {v: v for v in _TIPOS_VALIDOS if v != "DESCONHECIDO"}
_MAPA_NORMALIZACAO["DESCONHECIDO"] = "desconhecido"


class TipoSanguineoCreateSchema(BaseModel):
    tipo_sanguineo: Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "desconhecido"]

    @field_validator("tipo_sanguineo", mode="before")
    @classmethod
    def _normalizar_caixa(cls, v):
        if isinstance(v, str):
            chave = v.strip().upper()
            if chave in _MAPA_NORMALIZACAO:
                return _MAPA_NORMALIZACAO[chave]
        return v