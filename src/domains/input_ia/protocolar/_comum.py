"""Apoio compartilhado do grupo 'protocolar' (nao e um bloco: o '_' impede o registro).

Projecoes de InputProtocolo / InputProtocoloExecucao / ProtocoloCatalogo.
"""
from __future__ import annotations

from ..nucleo import iso, limpar

# So triagem e avaliacao-medica geram InputProtocolo; nos demais tipos a
# ausencia de protocolo nao e lacuna.
TIPOS_COM_PROTOCOLO = ("triagem", "avaliacao-medica")

_CHAVES_SCHEMA_RESULTADO = ("classificacao", "trilha_explicativa", "dados_ausentes", "metadata")


def vazio(v) -> bool:
    return v in (None, "", [], {})


def nomes(v) -> list[str]:
    """Lista de nomes a partir de JSON que pode ser lista, dict ou texto."""
    if vazio(v):
        return []
    if isinstance(v, dict):
        return [str(k) for k in v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if not vazio(x)]
    return [str(v)]


def inputs(at) -> list:
    """So o input VIGENTE do atendimento (lista com 0 ou 1 item).

    InputProtocolo e insert-only: o medico ajusta e reenvia, e o de maior id
    (em qualquer coleta do atendimento) e o que vale. Os substituidos ficam no
    banco, mas nao vao para a IA: nem as respostas, nem a queixa, nem as
    lacunas deles. Quem consome (protocolos, queixa_dados, protocolos_referencia,
    atendimentos_anteriores) herda a regra."""
    todos = [i for c in at.coletas_clinicas for i in c.inputs_protocolo]
    return [max(todos, key=lambda i: i.id)] if todos else []


def execucoes_validas(inp) -> list:
    """Ultima execucao NAO cancelada de cada protocolo (reexecucao substitui)."""
    ultimas = {}
    for e in sorted(inp.execucoes, key=lambda e: (e.timestamp_execucao, e.id)):
        if e.status != "cancelada":
            ultimas[e.id_protocolo_catalogo] = e
    return list(ultimas.values())


def resultado(res):
    """SchemaResultado serializado (classificacao, trilha_explicativa,
    dados_ausentes, metadata) -> projecao para IA. Outro formato passa limpo."""
    if not isinstance(res, dict):
        return limpar(res)
    passos = sorted((p for p in (res.get("trilha_explicativa") or []) if isinstance(p, dict)),
                    key=lambda p: p.get("ordem") or 0)
    extras = {k: v for k, v in res.items() if k not in _CHAVES_SCHEMA_RESULTADO}
    return limpar({
        "classificacao": res.get("classificacao"),
        "trilha": [{"rotulo": p.get("rotulo"),
                    "observado": p.get("valor_observado"),
                    "contribuicao": p.get("peso_ou_resultado")} for p in passos],
        "metadata": res.get("metadata"),
        **extras,
    })


def ausentes_da_execucao(e) -> list[str]:
    """dados_ausentes da execucao + os de dentro do resultado calculado."""
    res = e.resultado_calculado_json
    extra = nomes(res.get("dados_ausentes")) if isinstance(res, dict) else []
    return list(dict.fromkeys(nomes(e.dados_ausentes_json) + extra))


def protocolos(at) -> tuple[list[dict], list[str]]:
    """(itens, lacunas). Um item por InputProtocolo do atendimento."""
    itens, lacunas = [], []
    for inp in inputs(at):
        bruto = inp.input_json
        vazios = ([str(k) for k, v in bruto.items() if vazio(limpar(v))]
                  if isinstance(bruto, dict) else [])
        criticos = nomes(inp.dados_criticos_ausentes_json)
        execs = execucoes_validas(inp)
        rotulo = f"protocolo ({inp.tipo_input})"
        lacunas += [f"{rotulo}: dado critico ausente: {x}" for x in criticos]
        if not execs:
            lacunas.append(f"{rotulo}: sem execucao valida")
        projetadas = []
        for e in execs:
            cat = e.protocolo_catalogo
            nome = cat.nome_protocolo if cat else None
            ausentes = ausentes_da_execucao(e)
            etiqueta = f"protocolo {nome}" if nome else "protocolo"
            lacunas += [f"{etiqueta}: dado ausente: {x}" for x in ausentes]
            projetadas.append(limpar({
                "protocolo": nome,
                "sigla": cat.sigla if cat else None,
                "status": e.status,
                "executada_em": iso(e.timestamp_execucao),
                "dados_ausentes": ausentes,
                "resultado_deterministico": resultado(e.resultado_calculado_json),
                "resultado_parcial": True if e.status == "incompleta" else None,
            }))
        itens.append(limpar({
            "tipo": inp.tipo_input,
            "campos_preenchidos": bruto,
            "campos_vazios": vazios,
            "dados_criticos_ausentes": criticos,
            "execucoes": projetadas,
        }))
    return itens, list(dict.fromkeys(lacunas))


def queixa_dados(at) -> dict:
    ins = inputs(at)
    queixas = list(dict.fromkeys(
        i.queixa_principal.strip() for i in ins
        if i.queixa_principal and i.queixa_principal.strip()))
    avpus = [i.valor_avpu for i in ins if i.valor_avpu]
    return limpar({
        "queixa_principal": queixas[0] if len(queixas) == 1 else queixas,
        "avpu": avpus[-1] if avpus else None,
    })
