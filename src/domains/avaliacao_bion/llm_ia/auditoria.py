"""auditoria.py

Registro operacional de uma chamada à LLM e o destino que o recebe. Contém somente metadados técnicos
(provedor, modelo, versão do prompt, tokens, latência, custo estimado, se o preço do modelo é conhecido e status), nunca chave de API,
dado do paciente, prompt, resposta bruta nem texto de exceção. A implementação padrão grava no log estruturado.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("bion.ia.auditoria")


class RegistroAuditoriaLLM(BaseModel):
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
    preco_conhecido: bool = True
    status: Literal["sucesso", "erro_schema", "erro_provider", "circuit_breaker", "configuracao"]
    categoria_falha: Optional[str] = None
    simulado: bool = False
    uuid_output: Optional[str] = None


class AuditSink(Protocol):
    def registrar(self, registro: RegistroAuditoriaLLM) -> None:
        ...


class LlmAuditService:
    def registrar(self, registro: RegistroAuditoriaLLM) -> None:
        logger.info("chamada_llm", extra={"auditoria_llm": registro.model_dump(mode="json")})
