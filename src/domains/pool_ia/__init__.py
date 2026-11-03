"""__init__.py

Pacote da pool de metodos de leitura que a IA pode requisitar durante a avaliacao. Reune o contexto de execucao, o executor com limites e o registro de metodos.
"""
from .contexto import ContextoPool
from .pool import MAX_POR_RODADA, MAX_RODADAS, Pool
from .registro import Metodo, Retorno, descobrir, metodo

__all__ = ["ContextoPool", "MAX_POR_RODADA", "MAX_RODADAS", "Metodo", "Pool", "Retorno", "descobrir", "metodo"]
