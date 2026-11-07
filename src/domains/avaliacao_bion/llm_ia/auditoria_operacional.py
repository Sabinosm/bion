"""auditoria_operacional.py

Telemetria técnica de cada chamada ao modelo na avaliação da Bion: quem respondeu, quanto tempo levou, quantos
tokens consumiu e quanto isso custaria, além do resultado. Complementa, sem substituir, a auditoria própria da
Bion (RequisicaoIA). Grava só metadados no destino de auditoria do módulo de IA, nunca conteúdo clínico, prompt,
resposta do modelo ou texto de exceção, e nunca interrompe a avaliação: qualquer falha ao registrar é ignorada
com um aviso no log. A latência medida inclui as novas tentativas feitas pela camada de resiliência.
"""
from __future__ import annotations

import logging
import os

from .auditoria import AuditSink, LlmAuditService, RegistroAuditoriaLLM
from .cliente import ClienteIA, TurnoIA
from .cost_calculator import CostCalculator
from .exceptions import (
    CATEGORIA_ERRO_DESCONHECIDO,
    CircuitBreakerAbertoError,
    ConfiguracaoLLMInvalidaError,
    FalhaLLMError,
)

from .prompts.prescricao import VERSAO_PROMPT

log = logging.getLogger(__name__)

TIPO_ANALISE = "prescricao_bion"


def _calculadora() -> CostCalculator:
    try:
        return CostCalculator.do_ambiente(os.environ)
    except ConfiguracaoLLMInvalidaError:
        log.warning("LLM_PRECOS_POR_MILHAO invalida; usando a tabela padrao de precos")
        return CostCalculator()


class AuditoriaDaAvaliacao:
    """Emite um registro por chamada a `cliente.turno`, com o uuid da saída para correlacionar com OutputBion."""

    def __init__(self, cliente: ClienteIA, uuid_output: str | None = None, sink: AuditSink | None = None,
                 calculadora: CostCalculator | None = None):
        self._cliente = cliente
        self._uuid = uuid_output
        self._sink = sink or LlmAuditService()
        self._calc = calculadora or _calculadora()

    def turno(self, turno: TurnoIA, latencia_ms: int, *, resposta_valida: bool = True) -> None:
        """Chamada que voltou: `resposta_valida=False` marca a resposta final rejeitada pelo sistema."""
        uso = turno.uso
        provedor = uso.provedor if uso else self._provedor()
        modelo = uso.modelo if uso else (turno.versao_modelo or self._versao())
        self._emitir(
            provedor=provedor, modelo=modelo,
            temperatura=(uso.temperatura if uso and uso.temperatura is not None else self._temperatura()),
            tokens_entrada=uso.tokens_entrada if uso else 0, tokens_saida=uso.tokens_saida if uso else 0,
            latencia_ms=latencia_ms, simulado=uso.simulado if uso else self._simulado(),
            status="sucesso" if resposta_valida else "erro_schema",
            categoria_falha=None if resposta_valida else "resposta_rejeitada",
        )

    def falha(self, exc: BaseException, latencia_ms: int) -> None:
        """Chamada que lançou: a categoria vem da exceção classificada e nunca do texto dela."""
        if isinstance(exc, CircuitBreakerAbertoError):
            status = "circuit_breaker"
        elif isinstance(exc, ConfiguracaoLLMInvalidaError):
            status = "configuracao"
        else:
            status = "erro_provider"
        categoria = exc.categoria if isinstance(exc, FalhaLLMError) else CATEGORIA_ERRO_DESCONHECIDO
        self._emitir(provedor=self._provedor(), modelo=self._versao(), temperatura=self._temperatura(),
                     latencia_ms=latencia_ms, simulado=self._simulado(), status=status, categoria_falha=categoria)

    def _emitir(self, *, tokens_entrada: int = 0, tokens_saida: int = 0, modelo: str, **campos) -> None:
        try:
            self._sink.registrar(RegistroAuditoriaLLM(
                modelo=modelo, versao_prompt=f"v{VERSAO_PROMPT}", tipo_analise=TIPO_ANALISE,
                tokens_entrada=tokens_entrada, tokens_saida=tokens_saida,
                custo_estimado_usd=self._calc.estimar(modelo, tokens_entrada, tokens_saida),
                preco_conhecido=self._calc.preco_conhecido(modelo), uuid_output=self._uuid, **campos))
        except Exception:
            log.warning("falha ao registrar a auditoria operacional da chamada de IA", exc_info=True)

    def _provedor(self) -> str:
        return getattr(self._cliente, "provedor", None) or "desconhecido"

    def _versao(self) -> str:
        return getattr(self._cliente, "versao", None) or "desconhecido"

    def _temperatura(self) -> float:
        valor = getattr(self._cliente, "temperatura", None)
        return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else 0.0

    def _simulado(self) -> bool:
        return bool(getattr(self._cliente, "simulado", False))
