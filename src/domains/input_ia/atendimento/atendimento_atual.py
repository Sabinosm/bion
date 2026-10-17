"""Bloco 'atendimento': o atendimento em andamento."""
from __future__ import annotations

from ..nucleo import Bloco, iso, limpar
from ..registro import bloco

NOME = "atendimento"


@bloco(NOME, ordem=110,
       descricao="Atendimento atual: tipo, status, inicio, observacoes do profissional e habitos.")
def montar(at) -> Bloco:
    return Bloco(NOME, limpar({
        "tipo": at.tipo_atendimento,
        "status": at.status,
        "iniciado_em": iso(at.data_hora_inicio),
        "observacoes_profissional": at.observacoes_profissional,
        "habitos": at.habitos_atendimento_json,
    }))
