"""Este arquivo lê e valida a configuração do módulo de IA a partir de variáveis de ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

from .exceptions import ConfiguracaoLLMInvalidaError

PROVEDORES_SUPORTADOS = ("anthropic", "mock")
URL_ANTHROPIC = "https://api.anthropic.com/v1/messages"
MODELO_PADRAO = "claude-sonnet-4-6"
AMBIENTES_SEM_MOCK = ("production", "producao")


@dataclass(frozen=True)
class ConfiguracaoLLM:
    provedor: str = "anthropic"
    api_key: str = field(default="", repr=False)
    modelo: str = MODELO_PADRAO
    url_base: str = URL_ANTHROPIC
    anthropic_version: str = "2023-06-01"
    temperatura: float = 0.2
    max_tokens: int = 2000
    timeout_segundos: float = 30.0
    max_retries: int = 2
    versao_prompt: str = "v1"
    breaker_falhas: int = 5
    breaker_reset_segundos: float = 60.0
    ambiente: str = "development"

    def validar(self) -> "ConfiguracaoLLM":
        """Esta função devolve a própria configuração se válida, ou levanta ConfiguracaoLLMInvalidaError."""
        if self.provedor not in PROVEDORES_SUPORTADOS:
            raise ConfiguracaoLLMInvalidaError("LLM_PROVIDER", f"valores aceitos: {', '.join(PROVEDORES_SUPORTADOS)}")
        if self.provedor == "mock" and self.ambiente.lower() in AMBIENTES_SEM_MOCK:
            raise ConfiguracaoLLMInvalidaError("LLM_PROVIDER", "mock não é permitido em produção")
        if self.provedor != "mock":
            if not self.api_key.strip():
                raise ConfiguracaoLLMInvalidaError("LLM_API_KEY", "ausente")
            if not self.url_base.lower().startswith("https://"):
                raise ConfiguracaoLLMInvalidaError("LLM_URL", "deve usar https")
        if not self.modelo.strip():
            raise ConfiguracaoLLMInvalidaError("LLM_MODEL", "ausente")
        if not 0.0 <= self.temperatura <= 1.0:
            raise ConfiguracaoLLMInvalidaError("LLM_TEMPERATURE", "deve estar entre 0 e 1")
        if not 1 <= self.max_tokens <= 16000:
            raise ConfiguracaoLLMInvalidaError("LLM_MAX_TOKENS", "deve estar entre 1 e 16000")
        if not 1 <= self.timeout_segundos <= 120:
            raise ConfiguracaoLLMInvalidaError("LLM_TIMEOUT", "deve estar entre 1 e 120")
        if not 0 <= self.max_retries <= 5:
            raise ConfiguracaoLLMInvalidaError("LLM_MAX_RETRIES", "deve estar entre 0 e 5")
        if self.breaker_falhas < 1 or self.breaker_reset_segundos <= 0:
            raise ConfiguracaoLLMInvalidaError("LLM_BREAKER", "valores devem ser positivos")
        return self

    @classmethod
    def do_ambiente(cls, env: Optional[Mapping[str, str]] = None) -> "ConfiguracaoLLM":
        """Esta função lê as variáveis LLM_* do ambiente e valida o resultado."""
        env = os.environ if env is None else env

        def numero(nome: str, padrao, tipo):
            bruto = env.get(nome)
            if bruto is None or bruto == "":
                return padrao
            try:
                return tipo(bruto)
            except ValueError:
                raise ConfiguracaoLLMInvalidaError(nome, "valor numérico inválido") from None

        padrao = cls()
        return cls(
            provedor=env.get("LLM_PROVIDER", padrao.provedor).strip().lower(),
            api_key=env.get("LLM_API_KEY", ""),
            modelo=env.get("LLM_MODEL", padrao.modelo),
            url_base=env.get("LLM_URL", padrao.url_base),
            anthropic_version=env.get("LLM_ANTHROPIC_VERSION", padrao.anthropic_version),
            temperatura=numero("LLM_TEMPERATURE", padrao.temperatura, float),
            max_tokens=numero("LLM_MAX_TOKENS", padrao.max_tokens, int),
            timeout_segundos=numero("LLM_TIMEOUT", padrao.timeout_segundos, float),
            max_retries=numero("LLM_MAX_RETRIES", padrao.max_retries, int),
            versao_prompt=env.get("LLM_PROMPT_VERSION", padrao.versao_prompt),
            breaker_falhas=numero("LLM_BREAKER_FALHAS", padrao.breaker_falhas, int),
            breaker_reset_segundos=numero("LLM_BREAKER_RESET_SEGUNDOS", padrao.breaker_reset_segundos, float),
            ambiente=env.get("FLASK_ENV", padrao.ambiente),
        ).validar()
