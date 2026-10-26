"""Este arquivo implementa a explicação de triagem: só faz sentido quando há resultado de protocolo determinístico."""
from src.core.exceptions import DadosInvalidosError

from ..context.clinical_context import ContextoClinicoSeguro
from .analysis_strategy import AnalysisStrategy


class TriageExplanationStrategy(AnalysisStrategy):
    tipo = "explicacao_triagem"
    descricao = "Explica o resultado de triagem gerado pelos protocolos determinísticos, sem alterá-lo."

    def validar_contexto(self, contexto: ContextoClinicoSeguro) -> None:
        if not contexto.possui_resultado_protocolo():
            raise DadosInvalidosError(
                "explicacao_triagem exige o resultado de ao menos um protocolo de triagem.",
                campo="resultado_triagem",
            )
