"""Bloco 'doenca_cronica': doencas cronicas vigentes."""
from __future__ import annotations

from datetime import date

from ..nucleo import Bloco, bloco_lista, iso, limpar
from ..registro import bloco

NOME = "doenca_cronica"


@bloco(NOME, ordem=30,
       descricao="Doencas cronicas vigentes do paciente (CID-10, desde quando, status).")
def montar(at) -> Bloco:
    abertas = [d for d in at.consulta.paciente.doencas if d.aberta]
    abertas.sort(key=lambda d: d.desde or date.min)
    itens = [limpar({
        "cid10": d.codigo_cid10,
        "descricao": d.descricao_cid10,
        "desde": iso(d.desde),
        "status": d.status,
        "observacoes": d.observacoes,
    }) for d in abertas]
    return bloco_lista(NOME, itens, at.binario)
