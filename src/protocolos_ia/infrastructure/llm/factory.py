"""Este arquivo cria o provedor de LLM correto a partir da configuração. É o único lugar que conhece as implementações concretas."""
from __future__ import annotations

from typing import Optional

from .config import ConfiguracaoLLM
from .providers.anthropic_provider import AnthropicProvider
from .providers.mock_provider import MockProvider


class LLMProviderFactory:
    @staticmethod
    def criar(config: Optional[ConfiguracaoLLM] = None):
        """Esta função valida a configuração (do ambiente, se não informada) e devolve o provedor. O mock exige escolha explícita."""
        config = (config or ConfiguracaoLLM.do_ambiente()).validar()
        if config.provedor == "mock":
            return MockProvider()
        return AnthropicProvider(config)
