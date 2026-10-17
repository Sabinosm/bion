"""Bloco 'queixa': queixa principal e AVPU."""
from __future__ import annotations

from ..nucleo import Bloco
from ..registro import bloco
from ._comum import TIPOS_COM_PROTOCOLO, queixa_dados

NOME = "queixa"


@bloco(NOME, ordem=200, descricao="Queixa principal do paciente e nivel AVPU.")
def montar(at) -> Bloco:
    dados = queixa_dados(at)
    if "queixa_principal" in dados:
        return Bloco(NOME, dados)
    if at.tipo_atendimento in TIPOS_COM_PROTOCOLO:
        return Bloco(NOME, {"status": "nao_informado", **dados}, ("queixa: nao informada",))
    return Bloco(NOME, {"status": "nao_se_aplica", **dados})
