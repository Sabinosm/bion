"""Bloco 'tipo_sanguineo': tipo sanguineo mais recente."""
from __future__ import annotations

from ..nucleo import Bloco, bloco_lista
from ..registro import bloco

NOME = "tipo_sanguineo"


@bloco(NOME, ordem=50, descricao="Tipo sanguineo mais recente do paciente.")
def montar(at) -> Bloco:
    tipo = at.consulta.paciente.tipo_sanguineo
    itens = [{"tipo": tipo}] if tipo and tipo != "desconhecido" else []
    return bloco_lista(NOME, itens, at.binario)
