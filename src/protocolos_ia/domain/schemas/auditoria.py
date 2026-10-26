"""Registro operacional de uma chamada à LLM. Contém somente metadados técnicos."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class RegistroAuditoriaLLM(BaseModel):
    """Nunca recebe chave de API, dado do paciente, prompt, resposta bruta nem texto de exceção."""

    model_config = ConfigDict(extra="forbid")

    provedor: str
    modelo: str
    versao_prompt: str
    tipo_analise: str
    temperatura: float
    tokens_entrada: int = 0
    tokens_saida: int = 0
    latencia_ms: int = 0
    custo_estimado_usd: float = 0.0
    status: Literal["sucesso", "erro_schema", "erro_provider", "circuit_breaker", "configuracao"]
    categoria_falha: Optional[str] = None
    simulado: bool = False
    uuid_output: Optional[str] = None
