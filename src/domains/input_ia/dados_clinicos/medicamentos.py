"""Bloco 'medicamentos': medicamentos em uso."""
from __future__ import annotations

from ..nucleo import Bloco, bloco_lista, iso, limpar
from ..registro import bloco

NOME = "medicamentos"


@bloco(NOME, ordem=40,
       descricao="Medicamentos em uso, com dose, frequencia e se entram na checagem de interacoes.")
def montar(at) -> Bloco:
    ativos = [m for m in at.consulta.paciente.medicamentos_em_uso if m.ativo]
    itens = []
    for m in ativos:
        cat = m.catalogo_medicamentos
        itens.append(limpar({
            "descricao": m.descricao,
            "principio_ativo": cat.principio_ativo if cat else None,
            "dose": m.dose,
            "frequencia": m.frequencia,
            "desde": iso(m.desde),
            # False = fora do catalogo: ninguem checou interacoes deste item
            "interacoes_verificaveis": m.id_catalogo is not None,
        }))
    return bloco_lista(NOME, itens, at.binario)
