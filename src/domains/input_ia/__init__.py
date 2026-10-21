"""Input para IA: uma caixa grande (InputModel) feita de caixas pequenas
(blocos) que se registram sozinhas. Ver registro.py para ampliar."""
from .config import IDIOMA_PADRAO, Config
from .indices import PESOS_CONFIANCA, Indices
from .input_model import InputModel
from .nucleo import Bloco, Sinal, Status, resolver_status
from .registro import bloco, descobrir, fabricas

__all__ = ["Bloco", "Config", "IDIOMA_PADRAO", "Indices", "InputModel", "PESOS_CONFIANCA",
           "Sinal", "Status", "bloco", "descobrir", "fabricas", "resolver_status"]