"""Bloco 'conduta_enfermagem': condutas registradas no atendimento atual."""
from __future__ import annotations

from ..nucleo import Bloco
from ..registro import bloco
from ._comum import condutas

NOME = "conduta_enfermagem"


@bloco(NOME, ordem=140,
       descricao="Condutas de enfermagem registradas no atendimento atual.")
def montar(at) -> Bloco:
    itens = condutas(at)
    if not itens:  # opcional: ausencia nao e lacuna
        return Bloco(NOME, {"status": "nenhuma_registrada"})
    return Bloco(NOME, {"condutas": itens})
