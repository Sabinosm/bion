"""Bloco 'alergias': alergias vigentes e suas reacoes."""
from __future__ import annotations

from ..nucleo import Bloco, Sinal, bloco_lista, iso, limpar
from ..registro import bloco

NOME = "alergias"
_ORDEM = {"grave": 3, "moderada": 2, "leve": 1}


@bloco(NOME, ordem=20,
       descricao="Alergias vigentes do paciente e suas reacoes, da mais grave para a mais leve.")
def montar(at) -> Bloco:
    ativas = [a for a in at.consulta.paciente.alergias if not a.deletado]
    ativas.sort(key=lambda a: _ORDEM.get(a.gravidade_maxima, 0), reverse=True)
    itens = [limpar({
        "substancia": a.substancia,
        "confirmada": a.flag_confirmado,
        "gravidade_maxima": a.gravidade_maxima,
        "reacoes": [{
            "manifestacao": r.manifestacao,
            "gravidade": r.gravidade,
            "descricao": r.descricao,
            "data": iso(r.data_ocorrencia),
        } for r in a.reacoes_ativas],
    }) for a in ativas]
    nao_confirmadas = sum(not a.flag_confirmado for a in ativas)
    return bloco_lista(NOME, itens, at.binario, sinais=(Sinal.ALERGIA_NAO_CONFIRMADA,) * nao_confirmadas)