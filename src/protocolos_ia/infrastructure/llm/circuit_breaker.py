"""Este arquivo implementa um circuit breaker simples e thread-safe, sem dependências externas.

O estado guardado é apenas operacional (contadores e horários). Nenhum dado clínico passa por aqui.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict

FECHADO = "fechado"
ABERTO = "aberto"
MEIO_ABERTO = "meio_aberto"


class CircuitBreaker:
    def __init__(self, falhas_max: int, reset_segundos: float, relogio: Callable[[], float] = time.monotonic):
        self._falhas_max = falhas_max
        self._reset = reset_segundos
        self._relogio = relogio
        self._lock = threading.Lock()
        self._falhas = 0
        self._estado = FECHADO
        self._aberto_em = 0.0
        self._teste_em_curso = False

    @property
    def estado(self) -> str:
        with self._lock:
            return self._estado

    def permitir(self) -> bool:
        """Esta função diz se uma chamada pode seguir. No estado meio-aberto só uma chamada de teste passa por vez."""
        with self._lock:
            if self._estado == FECHADO:
                return True
            if self._estado == ABERTO:
                if self._relogio() - self._aberto_em < self._reset:
                    return False
                self._estado = MEIO_ABERTO
                self._teste_em_curso = True
                return True
            if self._teste_em_curso:
                return False
            self._teste_em_curso = True
            return True

    def registrar_sucesso(self) -> None:
        with self._lock:
            self._falhas = 0
            self._estado = FECHADO
            self._teste_em_curso = False

    def registrar_falha(self) -> None:
        with self._lock:
            self._teste_em_curso = False
            self._falhas += 1
            if self._estado == MEIO_ABERTO or self._falhas >= self._falhas_max:
                self._estado = ABERTO
                self._aberto_em = self._relogio()


class RegistroDeBreakers:
    """Mantém um breaker por provedor e modelo, compartilhado entre as requisições do processo."""

    def __init__(self):
        self._lock = threading.Lock()
        self._breakers: Dict[str, CircuitBreaker] = {}

    def obter(self, chave: str, falhas_max: int, reset_segundos: float) -> CircuitBreaker:
        with self._lock:
            if chave not in self._breakers:
                self._breakers[chave] = CircuitBreaker(falhas_max, reset_segundos)
            return self._breakers[chave]

    def limpar(self) -> None:
        with self._lock:
            self._breakers.clear()


REGISTRO_GLOBAL = RegistroDeBreakers()
