"""Pool de metodos de leitura que a IA pode requisitar (so select, via repositorio)."""
from .contexto import ContextoPool
from .pool import MAX_POR_RODADA, MAX_RODADAS, Pool
from .registro import Metodo, Retorno, descobrir, metodo

__all__ = ["ContextoPool", "MAX_POR_RODADA", "MAX_RODADAS", "Metodo", "Pool", "Retorno", "descobrir", "metodo"]
