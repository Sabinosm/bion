"""Contrato entre a estratégia de análise e a infraestrutura de LLM."""
from pydantic import BaseModel, ConfigDict, Field


class LLMRequest(BaseModel):
    """Solicitação normalizada enviada ao provedor. O campo system leva as regras; prompt leva apenas dados não confiáveis delimitados."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tipo_analise: str = Field(min_length=1, max_length=100)
    versao_prompt: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9._-]+$")
    system: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
