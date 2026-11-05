"""detalhe_atendimento_service.py

JSON do detalhe de um Atendimento, para a página "Detalhes". Usa a mesma fonte
do PDF detalhado (a montagem dos dados do atendimento a partir do ORM) e os
mesmos rótulos e textos, então a página e o PDF nunca divergem e o front não
duplica vocabulário. Só muda o fim: em vez de desenhar um PDF, devolve
dicionários prontos para exibir, com as datas já formatadas no fuso da empresa.

Decisões: o detalhe não traz CPF nem data de nascimento do paciente (a página só
precisa de nome, idade e sexo); as datas vão como texto formatado, não ISO; os
números do back (Decimal) viram float e qualquer valor livre (respostas do
protocolo, hábitos) vira texto, porque o front usa só textContent; a leitura é
auditada no controller, ao contrário do PDF, que por decisão não é auditado.

Acesso: o mesmo do PDF (enfermeiro e médico da própria empresa, com 404 igual
para "não existe" e "é de outra empresa"). Não exige ser o dono do atendimento.

Arquivo PROVISÓRIO, ao lado do serviço de download do atendimento (mesma pasta).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.core.exceptions import RecursoNaoEncontradoError
from src.core.pdf_base import fmt_dt, fmt_duracao, humanizar
from src.core.pdf_clinico import tz_empresa
from src.domains.atendimento.repository import AtendimentoRepository
from src.domains.download.download_atendimento_service import (
    CERTEZA, ESTADO_BINARIO, FLAG_FAIXA, MOTIVO_CANCELAMENTO, ORIGEM, SECAO_BINARIO, SITIO, STATUS_ATENDIMENTO,
    STATUS_EXEC, TIPO_PRESCRICAO, URGENCIA, VITAL_ROTULO, DadosAtendimento, montar_dados_atendimento,
    vitais_resumidos, itens_contexto,
)

ORIGEM_BINARIO = {"manual": "Confirmado pelo profissional", "automatico": "Derivado do cadastro do paciente"}


def _txt(v: Any) -> Optional[str]:
    """Valor livre -> texto (None continua None)."""
    if v is None:
        return None
    return v if isinstance(v, str) else str(v)


def _num(v: Any) -> Optional[float]:
    """Decimal/str numérico -> float (None se vazio ou inválido)."""
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _fv(v: float) -> str:
    """Número no formato de exibição (sem zeros à direita, vírgula decimal)."""
    return f"{v:g}".replace(".", ",")


def _meta_execucao(ex: Dict[str, Any]) -> Dict[str, Any]:
    """O que o resultado de uma execução de protocolo SIGNIFICA, para a tela de resumo.

    - `explicacao`: texto fixo do protocolo (o que é / quando usar / como interpretar), do catálogo;
    - `acao_recomendada`, `escore_total`, `override_disparado`, `escore_parcial`: família escore (NEWS2);
    - `modulos` e `alertas`: família composta (um resultado por módulo; alertas = módulos-flag positivos).
    Tudo em texto/número/lista simples (o front só usa textContent). Chaves ausentes viram None/[]/False."""
    meta = ex.get("metadata") if isinstance(ex.get("metadata"), dict) else {}
    expl = ex.get("explicacao") if isinstance(ex.get("explicacao"), dict) else None
    agregacao = meta.get("agregacao") if isinstance(meta.get("agregacao"), dict) else {}

    modulos = []
    for m in meta.get("modulos") or []:
        if not isinstance(m, dict):
            continue
        saida = m.get("classificacao") if m.get("classificacao") is not None else m.get("valor")
        modulos.append({"sigla": _txt(m.get("sigla_modulo")), "status": _txt(m.get("status")),
                        "saida": _txt(saida), "motivo": _txt(m.get("motivo")),
                        "ausentes": [str(x) for x in (m.get("ausentes") or [])]})
    alertas = [{"modulo": _txt(a.get("modulo")), "classificacao": _txt(a.get("classificacao")),
                "motivo": _txt(a.get("motivo"))}
               for a in (meta.get("alertas") or []) if isinstance(a, dict)]
    return {
        "explicacao": ({k: _txt(expl.get(k)) for k in ("o_que_e", "quando_usar", "como_interpretar")}
                       if expl else None),
        "acao_recomendada": _txt(meta.get("acao_recomendada")),
        "escore_total": _num(meta.get("escore_total")),
        "override_disparado": bool(meta.get("override_disparado")),
        "resultado_parcial": bool(meta.get("escore_parcial") or agregacao.get("parcial")),
        "modulos": modulos, "alertas": alertas,
    }


def para_json(d: DadosAtendimento) -> Dict[str, Any]:
    """DadosAtendimento -> dict JSON-seguro, pronto para exibir. Função pura (testável sem banco)."""
    tz = d.tz

    def dt(v) -> Optional[str]:
        return fmt_dt(v, tz) if v else None

    p, pr = d.paciente, d.profissional

    # --- sinais vitais: resumo (última medição de cada um) + histórico completo
    sinais_resumo = [{"rotulo": rot, "valor": val, "fora": bool(fora)} for rot, val, fora in vitais_resumidos(d)]
    sinais = [{
        "rotulo": VITAL_ROTULO.get(v["tipo"], humanizar(v["tipo"])) + (" (escala DPOC)" if v["dpoc"] else ""),
        "valor": _fv(v["valor"]), "unidade": v["unidade"], "sitio": SITIO.get(v["sitio"], v["sitio"]),
        "quando_texto": dt(v["quando"]), "por": v["por"],
        "validacao": FLAG_FAIXA.get(v["flag"], v["flag"]), "fora": v["flag"] != "dentro-do-limite",
    } for v in d.sinais]

    # --- binário (conferência) com os registros vigentes, no texto do PDF
    itens = itens_contexto(d)
    binario = []
    for sec, rotulo in SECAO_BINARIO.items():
        b = d.binario[sec]
        estado = ESTADO_BINARIO.get(b["estado"], "Pendente") if b["estado"] else "Pendente"
        if b["revisao"]:
            estado += f" ({(b['revisao'] or {}).get('motivo') or 'motivo não informado'})"
        binario.append({"secao": sec, "rotulo": rotulo, "estado": estado, "estado_codigo": b["estado"],
                        "origem": ORIGEM_BINARIO.get(b["origem"], "-"), "itens": list(itens.get(sec, []))})

    # --- protocolo
    protocolo = None
    if d.protocolos or d.respostas_protocolo:
        protocolo = {
            "versoes_anteriores_input": d.versoes_anteriores_input,
            "respostas": [{"campo": humanizar(k), "resposta": _txt(v)} for k, v in d.respostas_protocolo.items()],
            "execucoes": [{
                "nome": ex["nome"], "versao": ex["versao"], "status": STATUS_EXEC.get(ex["status"], ex["status"]),
                "executado_texto": dt(ex["executado_em"]), "executor": ex["executor"],
                "classificacao": _txt(ex["classificacao"]),
                "trilha": [{"ordem": tp.get("ordem"), "rotulo": _txt(tp.get("rotulo")),
                            "valor_observado": _txt(tp.get("valor_observado")),
                            "resultado": _txt(tp.get("peso_ou_resultado"))}
                           for tp in sorted(ex["trilha"], key=lambda x: x.get("ordem", 0)) if isinstance(tp, dict)],
                "dados_ausentes": [str(x) for x in ex["dados_ausentes"]],
                **_meta_execucao(ex),
            } for ex in d.protocolos],
        }

    condutas = [{"quando_texto": dt(c["quando"]), "autor": c["autor"], "funcao": c["funcao"],
                 "protocolo": c["protocolo"], "descricao": c["descricao"]} for c in d.condutas]

    ia = [{
        "quando_texto": dt(o["quando"]), "status": o["status"], "erro": o["erro"], "modelo": o["modelo"],
        "completude": _num(o["completude"]), "confianca": _num(o["confianca"]),
        "explicacao": o["explicacao"], "precisa_mais_informacao": o["precisa_mais_informacao"],
        "perguntas": [str(x) for x in o["perguntas"] if x], "blocos": [str(x) for x in o["blocos"]],
        "propos_conduta": o["propos_conduta"],
    } for o in d.ia]

    resultados = []
    for r in d.resultados:
        resultados.append({
            "uuid": r["uuid"], "cid": r["cid"], "descricao": r["descricao"],
            "certeza": CERTEZA.get(r["certeza"], r["certeza"]),
            "tipo": TIPO_PRESCRICAO.get(r["tipo"], r["tipo"]) if r["tipo"] else None,
            "status": r["status"], "origem": ORIGEM.get(r["origem"], r["origem"]) if r["origem"] else None,
            "formulado_por": r["formulado_por"], "formulado_texto": dt(r["formulado_em"]),
            "confirmado_texto": dt(r["confirmado_em"]),
            "descartado_texto": dt(r["descartado_em"]), "descartado_por": r["descartado_por"],
            "motivo_descarte": r["motivo_descarte"], "consistente": r["consistente"],
            "medicamentos": [{"nome": m["nome"], "dose": m["dose"], "frequencia": m["frequencia"],
                              "duracao": m["duracao"], "orientacoes": m["orientacoes"],
                              "origem": ORIGEM.get(m["origem"], m["origem"])} for m in r["medicamentos"]],
            "exames": [{"nome": x["nome"], "urgencia": URGENCIA.get(x["urgencia"], x["urgencia"]),
                        "justificativa": x["justificativa"], "origem": ORIGEM.get(x["origem"], x["origem"])}
                       for x in r["exames"]],
        })

    return {
        "uuid": d.uuid, "consulta_uuid": d.consulta_uuid,
        "tipo": d.tipo, "tipo_rotulo": d.rotulo,
        "status": d.status, "status_rotulo": STATUS_ATENDIMENTO.get(d.status, d.status),
        "parcial": d.status == "em-andamento",
        "motivo_cancelamento": (MOTIVO_CANCELAMENTO.get(d.motivo_cancelamento, "não informado")
                                if d.status == "cancelado" else None),
        "inicio_texto": dt(d.inicio), "fim_texto": dt(d.fim),
        "duracao_texto": fmt_duracao(d.inicio, d.fim) if d.fim else None,
        "paciente": {
            "nome": p["nome"], "identificado": bool(p["identificado"]), "idade": p["idade"], "sexo": p["sexo"],
            "peso": _num(p["peso"]), "altura": _num(p["altura"]),
        },
        "profissional": {"nome": pr["nome"], "funcao": pr["funcao"], "registro": pr["registro"]},
        "queixa": {"principal": d.queixa, "sintomas_ha_horas": d.desde_quando_sintomas, "avpu": d.avpu},
        "sinais_resumo": sinais_resumo, "sinais": sinais,
        "binario": binario, "protocolo": protocolo, "condutas": condutas, "ia": ia, "resultados": resultados,
        "observacoes": d.observacoes,
        "habitos": [{"campo": humanizar(k), "informacao": _txt(v)} for k, v in (d.habitos or {}).items()],
    }


class DetalheAtendimentoService:

    def __init__(self):
        self.repo = AtendimentoRepository()

    def obter(self, uuid_atendimento: str, id_empresa: int, id_usuario: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """Devolve (detalhe, uuid_paciente). O detalhe inclui `e_meu`: o atendimento é do usuário
        logado (o front só mostra o atalho da prescrição ao dono, sem precisar do uuid do profissional).

        Raises:
            RecursoNaoEncontradoError: 404 igual para 'não existe' e 'é de outra empresa'.
        """
        a = self.repo.find_by_uuid(uuid_atendimento, id_empresa)
        if not a:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        agora = datetime.now(timezone.utc)
        paciente = a.consulta.paciente
        tz = tz_empresa(paciente.empresa)
        d = montar_dados_atendimento(a, tz, agora)
        dados = para_json(d)
        dados["e_meu"] = a.realizado_por == id_usuario
        return dados, (paciente.uuid if paciente else None)