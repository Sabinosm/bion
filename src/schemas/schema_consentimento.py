"""
Schema Pydantic de ENTRADA para consentimento LGPD.

O Literal de `canal_coleta` é cópia manual do db.Enum de Consentimento
-- não há introspecção automática do schema do banco aqui. Se o Enum
do model mudar, este arquivo precisa ser atualizado junto.

motivo (dispensa/revogação) tem strip + rejeição de string só-espaços.
hash_documento é validado como hex de 64 caracteres (SHA-256), formato
assumido pelo domínio -- ajustar aqui se o algoritmo usado mudar.
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

_REGEX_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


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


def _validar_texto_obrigatorio(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("não pode ser vazio ou só espaços")
    return v


class ConsentimentoCreateSchema(BaseModel):
    versao_termo: str = Field(min_length=1, max_length=50)
    canal_coleta: Literal["presencial-papel", "presencial-digital", "portal-online", "totem"]
    escopo_consentimento: Optional[dict] = None
    hash_documento: Optional[str] = Field(default=None, max_length=64)

    @field_validator("versao_termo")
    @classmethod
    def _versao_termo_sem_espacos_vazios(cls, v: str) -> str:
        return _validar_texto_obrigatorio(v)

    @field_validator("hash_documento")
    @classmethod
    def _hash_documento_formato_valido(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not _REGEX_SHA256_HEX.match(v):
            raise ValueError(
                "formato inválido -- esperado hash SHA-256 em hexadecimal (64 caracteres)"
            )
        return v.lower()


class ConsentimentoDispensaEmergenciaSchema(BaseModel):
    """Entrada para dispensar consentimento por urgência/emergência --
    fluxo separado de ConsentimentoCreateSchema porque os campos
    exigidos são outros (motivo é obrigatório aqui; não exige
    canal_coleta/versao_termo, já que não houve coleta de fato)."""
    motivo: str = Field(min_length=1, max_length=1000)

    @field_validator("motivo")
    @classmethod
    def _motivo_sem_espacos_vazios(cls, v: str) -> str:
        return _validar_texto_obrigatorio(v)


class ConsentimentoRevogarSchema(BaseModel):
    """motivo é obrigatório -- consistente com
    ConsentimentoDispensaEmergenciaSchema. Revogação é um evento que
    merece ficar registrado com uma razão de verdade, não um texto
    padrão genérico."""
    motivo: str = Field(min_length=1, max_length=1000)

    @field_validator("motivo")
    @classmethod
    def _motivo_sem_espacos_vazios(cls, v: str) -> str:
        return _validar_texto_obrigatorio(v)