"""Bloco 'protocolo': inputs e execucoes dos protocolos do atendimento atual."""
from __future__ import annotations

from ..nucleo import Bloco, Sinal
from ..registro import bloco
from ._comum import TIPOS_COM_PROTOCOLO, protocolos

NOME = "protocolo"


@bloco(NOME, ordem=210,
       descricao="Inputs e execucoes dos protocolos: campos preenchidos e vazios, "
                 "resultado deterministico, trilha e dados ausentes.")
def montar(at) -> Bloco:
    itens, lacunas = protocolos(at)
    aplicavel = at.tipo_atendimento in TIPOS_COM_PROTOCOLO
    if not itens:
        if aplicavel:
            return Bloco(NOME, {"status": "nao_informado"}, ("protocolo: nenhum input registrado",),
                         esperados=1, presentes=0)
        return Bloco(NOME, {"status": "nao_se_aplica"})

    campos = preenchidos = 0
    sinais: list[str] = []
    for it in itens:
        pre = it.get("campos_preenchidos")
        n_pre = len(pre) if isinstance(pre, dict) else 0
        campos += n_pre + len(it.get("campos_vazios") or [])
        preenchidos += n_pre
        sinais += [Sinal.DADO_CRITICO_AUSENTE] * len(it.get("dados_criticos_ausentes") or [])
        sinais += [Sinal.PROTOCOLO_INCOMPLETO] * sum(
            1 for e in it.get("execucoes") or [] if e.get("status") == "incompleta")
    if campos == 0:  # sem campos conhecidos: conta a existencia de execucao valida
        campos = 1
        preenchidos = 1 if any(it.get("execucoes") for it in itens) else 0
    return Bloco(NOME, {"itens": itens}, tuple(lacunas),
                 esperados=campos if aplicavel else 0,
                 presentes=preenchidos if aplicavel else 0, sinais=tuple(sinais))