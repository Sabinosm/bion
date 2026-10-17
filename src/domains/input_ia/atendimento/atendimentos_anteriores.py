"""Bloco 'atendimentos_anteriores': o historico da mesma consulta."""
from __future__ import annotations

from ..nucleo import Bloco, iso, limpar
from ..protocolar._comum import protocolos, queixa_dados
from ..registro import bloco
from ._comum import anteriores, coletas, condutas, ultimos_sinais

NOME = "atendimentos_anteriores"


@bloco(NOME, ordem=300,
       descricao="Atendimentos anteriores da mesma consulta, cada um com coletas, condutas, "
                 "queixa, protocolos e sinais vitais.")
def montar(at) -> Bloco:
    """Cada um com sua propria coleta e o ultimo valor de cada sinal vital."""
    ants = anteriores(at)
    if not ants:
        return Bloco(NOME, {"status": "nenhum"})  # normal, nao e lacuna
    itens = [limpar({
        "tipo": a.tipo_atendimento,
        "status": a.status,
        "iniciado_em": iso(a.data_hora_inicio),
        "finalizado_em": iso(a.data_hora_fim),
        "observacoes_profissional": a.observacoes_profissional,
        "coletas": coletas(a),
        "condutas_enfermagem": condutas(a),
        "queixa": queixa_dados(a),
        "protocolos": protocolos(a)[0],
        "sinais_vitais": ultimos_sinais(a),
    }) for a in ants]
    return Bloco(NOME, {"itens": itens})
