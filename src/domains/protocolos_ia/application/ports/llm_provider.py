"""Este arquivo define os contratos que o caso de uso exige da infraestrutura de LLM."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ...domain.schemas.requests import LLMRequest
from ...domain.schemas.responses import RespostaLLM

if TYPE_CHECKING:
    from ...infrastructure.llm.raw_response import RawLLMResponse


class LLMProvider(Protocol):
    nome_provedor: str
    nome_modelo: str
    simulado: bool

    def executar(self, request: LLMRequest) -> "RawLLMResponse":
        ...


class ExecutorLLM(Protocol):
    """Chama o provedor aplicando retry e circuit breaker."""

    def __call__(self, provider: LLMProvider, request: LLMRequest) -> "RawLLMResponse":
        ...


class ParserResposta(Protocol):
    def parsear(self, texto: str) -> RespostaLLM:
        ...
