"""__init__.py

Provedores concretos de LLM do modulo: Anthropic (real) e Mock (simulado, para desenvolvimento e testes).
"""
from .anthropic_provider import AnthropicProvider
from .mock_provider import MockProvider

__all__ = ["AnthropicProvider", "MockProvider"]
