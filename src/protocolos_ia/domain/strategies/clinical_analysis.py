"""Este arquivo implementa a análise clínica geral: exige apenas algum dado clínico real."""
from ..context.clinical_context import ContextoClinicoSeguro
from .analysis_strategy import AnalysisStrategy


class ClinicalAnalysisStrategy(AnalysisStrategy):
    tipo = "analise_clinica"
    descricao = "Resumo clínico, hipóteses, alertas e exames sugeridos."

    def validar_contexto(self, contexto: ContextoClinicoSeguro) -> None:
        self.exigir_conteudo_clinico(contexto)
