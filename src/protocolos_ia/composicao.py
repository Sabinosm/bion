"""Este arquivo monta o LLMAnalysisService com as implementações concretas. É o único ponto que liga as camadas."""
from __future__ import annotations

from functools import lru_cache

from .application.services.llm_analysis_service import LLMAnalysisService
from .infrastructure.audit.llm_audit_service import LlmAuditService
from .infrastructure.llm.config import ConfiguracaoLLM
from .infrastructure.llm.cost_calculator import CostCalculator
from .infrastructure.llm.factory import LLMProviderFactory
from .infrastructure.llm.resilience import ExecutorResiliente
from .infrastructure.llm.response_parser import ResponseParser
from .infrastructure.prompts.prompt_service import PromptService
from .infrastructure.repositories.output_bion_adapter import OutputBionAdapter
from .application.ports.llm_provider import LLMProvider
from .infrastructure.llm.exceptions import ConfiguracaoLLMInvalidaError


@lru_cache(maxsize=1)
def _prompt_service() -> PromptService:
    return PromptService()


def montar_servico_llm() -> LLMAnalysisService:
    """Esta função lê a configuração do ambiente a cada requisição e devolve um serviço novo. O estado compartilhado é só o do circuit breaker."""
    try:
        config = ConfiguracaoLLM.do_ambiente()
    except ConfiguracaoLLMInvalidaError as erro:
        config = None
        falha = erro

    def provider_factory() -> LLMProvider:
        if config is None:
            raise falha
        return LLMProviderFactory.criar(config)

    base = config or ConfiguracaoLLM()
    return LLMAnalysisService(
        provider_factory=provider_factory,
        prompt_source=_prompt_service(),
        repo=OutputBionAdapter(),
        audit=LlmAuditService(),
        executor=ExecutorResiliente(
            max_retries=base.max_retries,
            breaker_falhas=base.breaker_falhas,
            breaker_reset_segundos=base.breaker_reset_segundos,
        ),
        parser=ResponseParser(),
        versao_prompt=base.versao_prompt,
        temperatura=base.temperatura,
        estimar_custo=CostCalculator().estimar,
    )
