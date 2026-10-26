"""Avaliacao Bion: liga a rota ao input, a pool, a IA, a validacao e a gravacao."""
from .helpers.avaliador import Avaliacao, avaliar
from .helpers.cliente import ClienteIA, ClienteIAFalso, ClienteIAIndisponivel, PedidoFerramenta, TurnoIA, pede, responde
from .helpers.tarefa import Tarefa

__all__ = ["Avaliacao", "ClienteIA", "ClienteIAFalso", "ClienteIAIndisponivel", "PedidoFerramenta",
           "Tarefa", "TurnoIA", "avaliar", "pede", "responde", "bp_bion"]


def __getattr__(nome):
    """Carrega o blueprint somente quando solicitado, evitando importar Flask ao importar contratos puros."""
    if nome == "bp_bion":
        from .controller import bp_bion
        return bp_bion
    raise AttributeError(f"{__name__!r} não possui atributo {nome!r}")