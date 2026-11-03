"""__init__.py

Pacote do input da IA: uma caixa grande (InputModel) composta por caixas pequenas (blocos) que se registram sozinhas. Expoe a configuracao, o calculo de indices e o contrato de bloco.
"""
from .config import IDIOMA_PADRAO, Config
from .indices import PESOS_CONFIANCA, Indices
from .input_model import InputModel
from .nucleo import Bloco, Sinal, Status, resolver_status
from .registro import bloco, descobrir, fabricas

__all__ = ["Bloco", "Config", "IDIOMA_PADRAO", "Indices", "InputModel", "PESOS_CONFIANCA",
           "Sinal", "Status", "bloco", "descobrir", "fabricas", "resolver_status"]
