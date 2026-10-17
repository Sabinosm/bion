"""Bloco 'sinais_vitais': ultima medicao valida de cada tipo no atendimento atual."""
from __future__ import annotations

from ..nucleo import Bloco
from ..registro import bloco
from ._comum import SINAIS_ESPERADOS, ultimos_sinais

NOME = "sinais_vitais"


@bloco(NOME, ordem=130,
       descricao="Ultima medicao valida de cada sinal vital no atendimento atual, com alertas.")
def montar(at) -> Bloco:
    medicoes = ultimos_sinais(at)
    lacunas = tuple(f"sinais_vitais: {t}" for t in SINAIS_ESPERADOS if t not in medicoes)
    if not medicoes:
        return Bloco(NOME, {"status": "nao_informado"}, lacunas)
    return Bloco(NOME, {"medicoes": medicoes}, lacunas)
