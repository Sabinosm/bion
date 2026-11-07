"""resilience.py

Este arquivo aplica retry com backoff e circuit breaker a uma chamada de provedor. É a única camada de resiliência dos módulos de IA.

Também monta o executor a partir das variáveis LLM_* de retry e breaker, sem exigir chave nem provedor, para que um único conjunto de parâmetros valha para qualquer modelo.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Mapping, Optional

from .circuit_breaker import REGISTRO_GLOBAL, RegistroDeBreakers
from .config import ConfiguracaoLLM
from .exceptions import (
    CircuitBreakerAbertoError,
    ConfiguracaoLLMInvalidaError,
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

    def __call__(self, provider, request: Any) -> RawLLMResponse:
        """`request` e opaco aqui: LLMRequest (analise) ou RequisicaoTurno (avaliacao); so o provedor o interpreta."""
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


def executor_do_ambiente(env: Optional[Mapping[str, str]] = None) -> ExecutorResiliente:
    """Cria o executor a partir de LLM_MAX_RETRIES, LLM_BREAKER_FALHAS e LLM_BREAKER_RESET_SEGUNDOS, com os padrões e limites de ConfiguracaoLLM."""
    env = os.environ if env is None else env
    padrao = ConfiguracaoLLM()

    def numero(nome: str, valor_padrao, tipo):
        bruto = env.get(nome)
        if bruto is None or bruto == "":
            return valor_padrao
        try:
            return tipo(bruto)
        except ValueError:
            raise ConfiguracaoLLMInvalidaError(nome, "valor numérico inválido") from None

    max_retries = numero("LLM_MAX_RETRIES", padrao.max_retries, int)
    falhas = numero("LLM_BREAKER_FALHAS", padrao.breaker_falhas, int)
    reset = numero("LLM_BREAKER_RESET_SEGUNDOS", padrao.breaker_reset_segundos, float)
    if not 0 <= max_retries <= 5:
        raise ConfiguracaoLLMInvalidaError("LLM_MAX_RETRIES", "deve estar entre 0 e 5")
    if falhas < 1 or reset <= 0:
        raise ConfiguracaoLLMInvalidaError("LLM_BREAKER", "valores devem ser positivos")
    return ExecutorResiliente(max_retries=max_retries, breaker_falhas=falhas, breaker_reset_segundos=reset)
