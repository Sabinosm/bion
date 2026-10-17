"""Bloco 'coleta_clinica': coletas do atendimento atual."""
from __future__ import annotations

from ..nucleo import Bloco
from ..registro import bloco
from ._comum import coletas

NOME = "coleta_clinica"


@bloco(NOME, ordem=120,
       descricao="Coleta clinica do atendimento atual (ha quanto tempo comecaram os sintomas).")
def montar(at) -> Bloco:
    itens = coletas(at)
    if not itens:
        return Bloco(NOME, {"status": "nao_informado"}, ("coleta_clinica: nao informado",))
    return Bloco(NOME, {"coletas": itens})
