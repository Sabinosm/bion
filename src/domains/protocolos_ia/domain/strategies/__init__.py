"""__init__.py

Estrategias de analise por LLM (clinica, explicacao de triagem, hipoteses diferenciais) e o registro para obter a estrategia pelo tipo.
"""
from .analysis_strategy import AnalysisStrategy
from .registro import TIPO_PADRAO, obter_strategy, tipos_disponiveis

__all__ = ["AnalysisStrategy", "TIPO_PADRAO", "obter_strategy", "tipos_disponiveis"]
