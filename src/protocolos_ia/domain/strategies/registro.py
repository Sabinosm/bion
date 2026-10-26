"""Este arquivo mantém o registro explícito das estratégias disponíveis, sem registro por efeito colateral de import."""
from __future__ import annotations

from ..exceptions import TipoAnaliseInvalidoError
from .analysis_strategy import AnalysisStrategy
from .clinical_analysis import ClinicalAnalysisStrategy
from .differential_hypotheses import DifferentialHypothesesStrategy
from .triage_explanation import TriageExplanationStrategy

TIPO_PADRAO = ClinicalAnalysisStrategy.tipo

_ESTRATEGIAS: dict[str, AnalysisStrategy] = {
    s.tipo: s
    for s in (ClinicalAnalysisStrategy(), TriageExplanationStrategy(), DifferentialHypothesesStrategy())
}


def tipos_disponiveis() -> list[str]:
    return sorted(_ESTRATEGIAS)


def obter_strategy(tipo: str) -> AnalysisStrategy:
    """Esta função devolve a estratégia do tipo pedido ou levanta TipoAnaliseInvalidoError (422)."""
    estrategia = _ESTRATEGIAS.get(tipo)
    if estrategia is None:
        raise TipoAnaliseInvalidoError(tipos_disponiveis())
    return estrategia
