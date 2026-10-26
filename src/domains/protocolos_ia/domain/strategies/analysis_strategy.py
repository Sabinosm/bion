"""Este arquivo define o contrato das estratégias de análise: validar o contexto e montar a LLMRequest."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from src.core.exceptions import DadosInvalidosError

from ..context.clinical_context import ContextoClinicoSeguro, serializar_para_prompt
from ..ports.prompt_source import PromptSource
from ..schemas.requests import LLMRequest


class AnalysisStrategy(ABC):
    """Cada subclasse representa um tipo de análise com regras próprias de contexto mínimo."""

    tipo: ClassVar[str]
    descricao: ClassVar[str]

    @abstractmethod
    def validar_contexto(self, contexto: ContextoClinicoSeguro) -> None:
        """Levanta DadosInvalidosError quando o contexto não permite esta análise."""

    def montar_request(
        self, contexto: ContextoClinicoSeguro, prompt_source: PromptSource, versao_prompt: str
    ) -> LLMRequest:
        """Este método valida o contexto, serializa o JSON seguro e monta a solicitação com sistema e dados separados."""
        self.validar_contexto(contexto)
        prompt = prompt_source.montar(self.tipo, versao_prompt, serializar_para_prompt(contexto))
        return LLMRequest(
            tipo_analise=self.tipo,
            versao_prompt=versao_prompt,
            system=prompt.sistema,
            prompt=prompt.usuario,
        )

    @staticmethod
    def exigir_conteudo_clinico(contexto: ContextoClinicoSeguro) -> None:
        if not contexto.possui_conteudo_clinico():
            raise DadosInvalidosError(
                "Contexto clínico insuficiente para análise de IA: informe ao menos um dado clínico.",
                campo="contexto",
            )
