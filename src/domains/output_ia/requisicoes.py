"""Auditoria das requisicoes que a IA fez ao sistema (pool de metodos).

Vai na coluna JSON `requisicoes_ia_json` de OutputBion, uma lista com uma
entrada por requisicao. Texto longo (ex.: MedlinePlus) NAO entra: so o id e o
hash do conteudo, para provar o que a IA viu sem inflar a linha.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequisicaoIA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rodada: int = Field(ge=1)
    metodo: str = Field(min_length=1)
    argumentos: dict[str, Any] = Field(default_factory=dict)
    status: Literal["atendida", "recusada"]
    motivo: str | None = None                 # obrigatorio se recusada
    retorno: Any = None                       # resumo compacto do que voltou
    hash_conteudo: str | None = None          # para textos longos
    em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("motivo", mode="before")
    @classmethod
    def _branco(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _coerencia(self):
        if self.status == "recusada" and not self.motivo:
            raise ValueError("requisicao recusada exige 'motivo'.")
        return self


def colunas_requisicoes(requisicoes: list[RequisicaoIA | dict]) -> dict:
    itens = [r if isinstance(r, RequisicaoIA) else RequisicaoIA.model_validate(r) for r in requisicoes]
    return {"requisicoes_ia_json": [r.model_dump(mode="json") for r in itens]}
