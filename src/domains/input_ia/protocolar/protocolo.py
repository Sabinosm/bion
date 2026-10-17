"""Bloco 'protocolo': inputs e execucoes dos protocolos do atendimento atual."""
from __future__ import annotations

from ..nucleo import Bloco
from ..registro import bloco
from ._comum import TIPOS_COM_PROTOCOLO, protocolos

NOME = "protocolo"


@bloco(NOME, ordem=210,
       descricao="Inputs e execucoes dos protocolos: campos preenchidos e vazios, "
                 "resultado deterministico, trilha e dados ausentes.")
def montar(at) -> Bloco:
    itens, lacunas = protocolos(at)
    if not itens:
        if at.tipo_atendimento in TIPOS_COM_PROTOCOLO:
            return Bloco(NOME, {"status": "nao_informado"},
                         ("protocolo: nenhum input registrado",))
        return Bloco(NOME, {"status": "nao_se_aplica"})
    return Bloco(NOME, {"itens": itens}, tuple(lacunas))
