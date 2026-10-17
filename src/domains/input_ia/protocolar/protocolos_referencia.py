"""Bloco 'protocolos_referencia': explicacao estatica de cada protocolo usado."""
from __future__ import annotations

from ..atendimento._comum import anteriores
from ..nucleo import Bloco, limpar
from ..registro import bloco
from ._comum import execucoes_validas, inputs

NOME = "protocolos_referencia"


@bloco(NOME, ordem=220,
       descricao="Explicacao (o que e, quando usar, como interpretar) de cada protocolo usado "
                 "no atendimento atual e nos anteriores.")
def montar(at) -> Bloco:
    """UMA vez por protocolo. As execucoes referenciam pela sigla."""
    vistos = {}
    for a in [*anteriores(at), at]:
        for inp in inputs(a):
            for e in execucoes_validas(inp):
                cat = e.protocolo_catalogo
                if cat and cat.id not in vistos:
                    vistos[cat.id] = cat
    if not vistos:
        return Bloco(NOME, {"status": "nenhum"})
    itens = []
    for cat in vistos.values():
        exp = cat.explicacao_json if isinstance(cat.explicacao_json, dict) else {}
        itens.append(limpar({
            "sigla": cat.sigla,
            "nome": cat.nome_protocolo,
            "tipo_resultado": cat.tipo_resultado,
            "populacao": cat.escopo_populacao,
            "uso": cat.escopo_uso,
            "o_que_e": exp.get("o_que_e"),
            "quando_usar": exp.get("quando_usar"),
            "como_interpretar": exp.get("como_interpretar"),
            "explicacao": None if exp else cat.explicacao_json,
            "referencia": cat.referencia_bibliografica,
            "orgao_emissor": cat.orgao_emissor,
        }))
    return Bloco(NOME, {"itens": itens})
