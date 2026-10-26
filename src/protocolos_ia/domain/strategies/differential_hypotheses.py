"""Este arquivo implementa as hipóteses diferenciais: exige queixa principal ou sinais vitais informados."""
from src.core.exceptions import DadosInvalidosError

from ..context.clinical_context import ContextoClinicoSeguro
from .analysis_strategy import AnalysisStrategy


class DifferentialHypothesesStrategy(AnalysisStrategy):
    tipo = "hipoteses_diferenciais"
    descricao = "Hipóteses diagnósticas diferenciais ordenadas por criticidade."

    def validar_contexto(self, contexto: ContextoClinicoSeguro) -> None:
        if not (contexto.queixa_principal or contexto.sinais_vitais.itens):
            raise DadosInvalidosError(
                "hipoteses_diferenciais exige queixa_principal ou sinais_vitais.", campo="contexto"
            )
