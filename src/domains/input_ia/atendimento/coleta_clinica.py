"""Bloco 'coleta_clinica': coletas do atendimento atual."""
from __future__ import annotations

from ..nucleo import Bloco
from ..registro import bloco
from ._comum import coletas

NOME = "coleta_clinica"


@bloco(NOME, ordem=120,
       descricao="Coleta clinica do atendimento atual (ha quanto tempo comecaram os sintomas).")
def montar(at) -> Bloco:
    # coleta sem nenhum dado preenchido nao conta como informada
    itens = [c for c in coletas(at) if c]
    if not itens:
        return Bloco(NOME, {"status": "nao_informado"}, ("coleta_clinica: nao informado",),
                     esperados=1, presentes=0)
    return Bloco(NOME, {"coletas": itens}, esperados=1, presentes=1)