"""Bloco 'sinais_vitais': ultima medicao valida de cada tipo no atendimento atual."""
from __future__ import annotations

from ..nucleo import Bloco, Sinal
from ..registro import bloco
from ._comum import SINAIS_ESPERADOS, ultimos_sinais

NOME = "sinais_vitais"


@bloco(NOME, ordem=130,
       descricao="Ultima medicao valida de cada sinal vital no atendimento atual, com alertas.")
def montar(at) -> Bloco:
    medicoes = ultimos_sinais(at)
    lacunas = tuple(f"sinais_vitais: {t}" for t in SINAIS_ESPERADOS if t not in medicoes)
    presentes = sum(t in medicoes for t in SINAIS_ESPERADOS)
    sinais = (Sinal.SINAL_VITAL_FORA_DO_LIMITE,) * sum("alerta" in v for v in medicoes.values())
    dados = {"medicoes": medicoes} if medicoes else {"status": "nao_informado"}
    return Bloco(NOME, dados, lacunas, esperados=len(SINAIS_ESPERADOS), presentes=presentes, sinais=sinais)