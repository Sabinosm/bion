"""Este arquivo aplica retry com backoff e circuit breaker a uma chamada de provedor. É a única camada de resiliência do módulo."""
from __future__ import annotations

import time
from typing import Callable

from ...domain.schemas.requests import LLMRequest
from .circuit_breaker import REGISTRO_GLOBAL, RegistroDeBreakers
from .exceptions import (
    CircuitBreakerAbertoError,
    ErroPermanenteProvedor,
    ErroTransitorioProvedor,
    ProvedorIndisponivelError,
    RespostaLLMInvalidaError,
)
from .raw_response import RawLLMResponse


class ExecutorResiliente:
    """Esta classe executa provider.executar(request) com no máximo 1 + max_retries tentativas.

    Só falhas transitórias sofrem retry. Uma chamada lógica que esgota as tentativas conta uma falha no breaker.
    """

    def __init__(
        self,
        *,
        max_retries: int,
        breaker_falhas: int,
        breaker_reset_segundos: float,
        backoff_base: float = 1.0,
        backoff_maximo: float = 8.0,
        dormir: Callable[[float], None] = time.sleep,
        registro: RegistroDeBreakers = REGISTRO_GLOBAL,
    ):
        self._max_retries = max_retries
        self._falhas = breaker_falhas
        self._reset = breaker_reset_segundos
        self._base = backoff_base
        self._maximo = backoff_maximo
        self._dormir = dormir
        self._registro = registro

    def __call__(self, provider, request: LLMRequest) -> RawLLMResponse:
        breaker = self._registro.obter(f"{provider.nome_provedor}:{provider.nome_modelo}", self._falhas, self._reset)
        if not breaker.permitir():
            raise CircuitBreakerAbertoError()

        tentativa = 0
        while True:
            try:
                resposta = provider.executar(request)
            except ErroTransitorioProvedor as exc:
                if tentativa >= self._max_retries:
                    breaker.registrar_falha()
                    raise ProvedorIndisponivelError(detalhes="tentativas_esgotadas") from exc
                espera = self._base * (2 ** tentativa)
                if exc.retry_apos_segundos:
                    espera = max(espera, exc.retry_apos_segundos)
                self._dormir(min(espera, self._maximo))
                tentativa += 1
            except ErroPermanenteProvedor:
                breaker.registrar_sucesso()
                raise
            except RespostaLLMInvalidaError:
                breaker.registrar_sucesso()
                raise
            except Exception:
                breaker.registrar_falha()
                raise
            else:
                breaker.registrar_sucesso()
                return resposta
