"""Bloco 'consulta': o episodio inteiro."""
from __future__ import annotations

from ..nucleo import Bloco, iso, limpar
from ..registro import bloco

NOME = "consulta"


@bloco(NOME, ordem=100,
       descricao="Dados da consulta (episodio): origem, status e total de atendimentos.")
def montar(at) -> Bloco:
    c = at.consulta
    validos = [a for a in c.atendimentos if a.status != "cancelado"]
    return Bloco(NOME, limpar({
        "origem_encaminhamento": c.origem_encaminhamento,
        "status": c.status_consulta,
        "iniciada_em": iso(c.data_hora_inicio),
        "total_atendimentos": len(validos),
    }))
