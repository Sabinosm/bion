"""download_atendimento_service.py -- PDF de um Atendimento, em dois modos.

  detalhado -- auditoria/estudo: tudo que foi registrado, com autoria, horários, estado do
               binário, execução do protocolo, condutas, IA e prescrição. Sem enfeite.
  resumo    -- apresentável: o essencial em linguagem simples, seguro para entregar ao
               paciente (sem score técnico, sem trilha de IA, sem rascunhos).

O PDF é montado em memória a cada pedido e nunca vai a disco. Ele só REAPRESENTA dados que já
existem (por isso não é auditado, só leva data/dia/hora de emissão e quem emitiu).

Regras de acesso ao estado do atendimento:
  em-andamento -> detalhado sai com marca PARCIAL; resumo é bloqueado (409).
  cancelado    -> só o detalhado, com o motivo; resumo é bloqueado (409).
  finalizado   -> os dois.

Duas etapas, de propósito: `montar_dados_atendimento` lê o ORM e devolve um DadosAtendimento
(dicts simples); os `story_*` só desenham. A Consulta reaproveita as duas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from src.core.exceptions import ConflictoError, DadosInvalidosError, RecursoNaoEncontradoError
from src.core.pdf_base import (
    Estilos, Tema, TEMA_DETALHADO, TEMA_RESUMO, LARGURA_UTIL, P, PM, cartao, construir_pdf,
    esc, estilos, faixa_alerta, ficha, fmt_data, fmt_dt, fmt_duracao, fmt_hora, humanizar, idade_texto,
    mascarar_cpf, secao, tabela, data_extensa, vazio,
)
from src.core.pdf_clinico import (
    AVISO_LGPD_INTERNO, AVISO_RESUMO, ContextoClinico, attr, contexto_clinico_em, cpf_paciente, funcao_texto,
    moldura, nome_paciente, nome_usuario_por_id, registro_profissional, sexo_texto, tz_empresa,
)
from src.models.clinico import Binario
from src.domains.atendimento.repository import AtendimentoRepository

MODOS = ("detalhado", "resumo")

TIPO_ATENDIMENTO = {"triagem": "Triagem", "avaliacao-medica": "Avaliação médica",
                    "reavaliacao": "Reavaliação", "alta": "Alta", "procedimento": "Procedimento"}
STATUS_ATENDIMENTO = {"em-andamento": "Em andamento", "finalizado": "Finalizado", "cancelado": "Cancelado"}
MOTIVO_CANCELAMENTO = {"erro-abertura": "Aberto por engano", "paciente-nao-compareceu": "Paciente não compareceu",
                       "paciente-recusou": "Paciente recusou", "transferencia": "Transferência", "outro": "Outro"}
SECAO_BINARIO = {"alergias": "Alergias", "medicamentos": "Medicamentos em uso",
                 "tipo_sanguineo": "Tipo sanguíneo", "doenca_cronica": "Doenças crônicas"}
ESTADO_BINARIO = {"preenchido": "Possui (registrado)", "nega": "Nega", "nao-coletado": "Não coletado",
                  "requer-revisao": "REQUER REVISÃO"}
VITAL_ROTULO = {"frequencia-respiratoria": "Frequência respiratória", "spo2": "Saturação de O2 (SpO2)",
                "pa-sistolica": "PA sistólica", "pa-diastolica": "PA diastólica",
                "frequencia-cardiaca": "Frequência cardíaca", "temperatura": "Temperatura",
                "glicemia-capilar": "Glicemia capilar"}
VITAL_ORDEM = list(VITAL_ROTULO)
SITIO = {"axilar": "axilar", "oral": "oral", "retal": "retal", "timpanico": "timpânico",
         "oximetria-digital": "oximetria digital", "manguito-braco-direito": "braço direito",
         "manguito-braco-esquerdo": "braço esquerdo"}
FLAG_FAIXA = {"dentro-do-limite": "Dentro do limite", "fora-limite-alertado": "Fora do limite (alertado)",
              "fora-limite-rejeitado": "Fora do limite (rejeitado)"}
CERTEZA = {"suspeito": "suspeito", "provavel": "provável", "confirmado": "confirmado", "descartado": "descartado"}
TIPO_PRESCRICAO = {"farmacologica": "Farmacológica", "nao-farmacologica": "Não farmacológica",
                   "encaminhamento": "Encaminhamento", "internacao": "Internação", "alta": "Alta"}
URGENCIA = {"rotina": "Rotina", "urgente": "Urgente", "emergencia": "Emergência"}
ORIGEM = {"medico": "Médico", "bion_ia": "Bion (IA)", "protocolo": "Protocolo"}
MANIFESTACAO = {"cutanea": "cutânea", "respiratoria": "respiratória", "anafilaxia": "anafilaxia",
                "gastrointestinal": "gastrointestinal", "cardiovascular": "cardiovascular", "sistemica": "sistêmica"}
GRAVIDADE = {"leve": "leve", "moderada": "moderada", "grave": "GRAVE"}
STATUS_EXEC = {"concluida": "concluída", "incompleta": "incompleta", "cancelada": "cancelada"}


# ============================================================================ dados
@dataclass
class DadosAtendimento:
    uuid: str
    tipo: str
    status: str
    inicio: Optional[datetime]
    fim: Optional[datetime]
    motivo_cancelamento: Optional[str]
    observacoes: Optional[str]
    habitos: Optional[dict]
    consulta_uuid: Optional[str]
    paciente: Dict[str, Any]
    profissional: Dict[str, Any]
    tz: Any
    queixa: Optional[str] = None
    desde_quando_sintomas: Optional[int] = None
    avpu: Optional[str] = None
    sinais: List[dict] = field(default_factory=list)
    binario: Dict[str, dict] = field(default_factory=dict)
    contexto: ContextoClinico = field(default_factory=ContextoClinico)
    respostas_protocolo: Dict[str, Any] = field(default_factory=dict)
    versoes_anteriores_input: int = 0
    protocolos: List[dict] = field(default_factory=list)
    condutas: List[dict] = field(default_factory=list)
    ia: List[dict] = field(default_factory=list)
    resultados: List[dict] = field(default_factory=list)

    @property
    def rotulo(self) -> str:
        return TIPO_ATENDIMENTO.get(self.tipo, self.tipo)


def _nome(usuario) -> Optional[str]:
    return attr(usuario, "nome_completo")


def _versao_texto(versao) -> str:
    if versao is None:
        return "-"
    return str(attr(versao, "numero_versao", "versao", "rotulo", default=f"id {attr(versao, 'id', default='?')}"))


def _dados_protocolos(input_vigente) -> List[dict]:
    saida = []
    for ex in (getattr(input_vigente, "execucoes", None) or []):
        res = ex.resultado_calculado_json if isinstance(ex.resultado_calculado_json, dict) else {}
        prot = ex.protocolo_catalogo
        saida.append({
            "nome": attr(prot, "nome", "nome_protocolo", "titulo", "codigo_protocolo", "codigo", default="Protocolo"),
            "tipo": attr(prot, "tipo_protocolo"),
            "versao": _versao_texto(ex.versao_utilizada),
            "status": ex.status,
            "executado_em": ex.timestamp_execucao,
            "executor": _nome(ex.usuario_executor),
            "classificacao": res.get("classificacao"),
            "trilha": res.get("trilha_explicativa") or [],
            "dados_ausentes": res.get("dados_ausentes") or ex.dados_ausentes_json or [],
        })
    return saida


def _dados_ia(outputs) -> List[dict]:
    saida = []
    for o in (outputs or []):
        j = o.output_ia_json if isinstance(o.output_ia_json, dict) else {}
        prop = j.get("proposta") if isinstance(j.get("proposta"), dict) else {}
        saida.append({
            "quando": attr(o, "criado_em", "data_hora", "data_hora_criacao"),
            "status": attr(o, "status"),
            "erro": attr(o, "erro_codigo"),
            "modelo": attr(o, "versao_modelo_ia"),
            "completude": attr(o, "indice_completude"),
            "confianca": attr(o, "indice_confianca"),
            "explicacao": j.get("detalhamento_explicacao"),
            "precisa_mais_informacao": j.get("precisa_mais_informacao"),
            "perguntas": [p.get("pergunta") for p in (j.get("perguntas_pendentes") or []) if isinstance(p, dict)],
            "blocos": j.get("blocos_considerados") or [],
            "propos_conduta": bool(prop.get("medicamentos") or prop.get("exames")),
        })
    return saida


def dados_resultado_prescricao(r) -> dict:
    """ResultadoPrescricao -> dict (usado aqui, na Consulta e na Prescrição)."""
    meds = []
    for p in (r.prescricoes or []):
        meds.append({"nome": attr(p.catalogo_medicamentos, "principio_ativo", default="Medicamento"),
                     "dose": p.dose, "frequencia": p.frequencia, "duracao": p.duracao,
                     "orientacoes": p.orientacoes, "origem": p.origem_sugestao})
    exs = []
    for e in (r.prescricoes_exame or []):
        exs.append({"nome": attr(e.catalogo_exame, "nome_exame", default="Exame"),
                    "material": attr(e.catalogo_exame, "material"), "tipo": attr(e.catalogo_exame, "tipo"),
                    "jejum_horas": attr(e.catalogo_exame, "jejum_horas"),
                    "urgencia": e.urgencia, "justificativa": e.justificativa, "origem": e.origem_sugestao})
    return {"uuid": r.uuid, "cid": r.codigo_cid10_principal, "descricao": r.descricao_cid10_principal,
            "certeza": r.certeza_diagnostica, "tipo": r.tipo_prescricao, "status": r.status,
            "formulado_por": _nome(r.usuario), "formulado_em": r.data_hora_formulacao,
            "confirmado_em": r.confirmado_em, "consistente": r.consistente_com_classificacao,
            "origem": attr(r, "origem_sugestao"),
            "descartado_em": attr(r, "descartado_em"), "motivo_descarte": attr(r, "motivo_descarte"),
            "descartado_por": nome_usuario_por_id(attr(r, "descartado_por")) if r.status == "descartado" else None,
            "medicamentos": meds, "exames": exs}


def dados_paciente(pac, ref: Optional[datetime]) -> Dict[str, Any]:
    """Identificação do paciente para os PDFs (idade calculada na data `ref`)."""
    nasc = attr(pac, "data_nascimento")
    return {"nome": nome_paciente(pac), "cpf": cpf_paciente(pac), "sexo": sexo_texto(attr(pac, "sexo_biologico")),
            "nascimento": nasc, "peso": attr(pac, "peso"), "altura": attr(pac, "altura"),
            "idade": idade_texto(nasc, ref),
            "identificado": not (getattr(pac, "nao_identificado", False) or getattr(pac, "pessoal", None) is None)}


def montar_dados_atendimento(a, tz, agora: datetime) -> DadosAtendimento:
    """Lê o Atendimento (e o que pende dele) e devolve dicts simples. Sem regra de layout."""
    consulta = a.consulta
    pac = consulta.paciente if consulta else None
    ref = a.data_hora_fim or agora                         # "momento" do contexto clínico
    ctx = contexto_clinico_em(pac, ref)

    prof = a.usuario
    d = DadosAtendimento(
        uuid=a.uuid, tipo=a.tipo_atendimento, status=a.status, inicio=a.data_hora_inicio, fim=a.data_hora_fim,
        motivo_cancelamento=a.motivo_cancelamento, observacoes=a.observacoes_profissional,
        habitos=a.habitos_atendimento_json if isinstance(a.habitos_atendimento_json, dict) else None,
        consulta_uuid=consulta.uuid if consulta else None,
        paciente=dados_paciente(pac, ref),
        profissional={"nome": _nome(prof), "funcao": funcao_texto(prof), "registro": registro_profissional(prof)},
        tz=tz, contexto=ctx,
    )

    # --- coleta/protocolo: insert-only, vigente = maior id no atendimento
    coletas = sorted(a.coletas_clinicas or [], key=lambda c: c.id)
    if coletas:
        d.desde_quando_sintomas = coletas[-1].desde_quando_sintomas
    inputs = sorted((i for c in coletas for i in (c.inputs_protocolo or [])), key=lambda i: i.id)
    if inputs:
        vig = inputs[-1]
        d.queixa, d.avpu = vig.queixa_principal, vig.valor_avpu
        d.respostas_protocolo = vig.input_json if isinstance(vig.input_json, dict) else {}
        d.versoes_anteriores_input = len(inputs) - 1
        d.protocolos = _dados_protocolos(vig)

    # --- sinais vitais
    for v in sorted(a.sinais_vitais or [], key=lambda s: (s.data_hora_medicao is None, s.data_hora_medicao)):
        d.sinais.append({"tipo": v.tipo_parametro, "valor": float(v.valor_numerico), "unidade": v.unidade,
                         "sitio": v.sitio_medicao, "quando": v.data_hora_medicao, "por": _nome(v.usuario),
                         "flag": v.flag_validacao_faixa, "dpoc": bool(v.flag_escala_dpoc)})

    # --- binário (estado + origem por seção)
    b = Binario.de_atendimento(a)
    for sec in SECAO_BINARIO:
        d.binario[sec] = {"estado": b.estado(sec), "origem": b.origem(sec), "revisao": b.revisao(sec)}

    d.condutas = [{"quando": c.criado_em, "autor": _nome(c.profissional), "funcao": c.funcao_clinica,
                   "descricao": c.descricao_conduta,
                   "protocolo": attr(c.protocolo_catalogo, "nome", "nome_protocolo", "titulo", "codigo")}
                  for c in sorted(a.condutas_enfermagem or [], key=lambda c: c.id)]
    d.ia = _dados_ia(a.outputs_bion)
    d.resultados = [dados_resultado_prescricao(r) for r in sorted(a.resultados_prescricao or [], key=lambda r: r.id)]
    return d


# ============================================================================ blocos
def _fv(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _lista(itens: List[str], e: Estilos) -> Paragraph:
    if not itens:
        return Paragraph("-", e.celula)
    return Paragraph("<br/>".join("• " + esc(i) for i in itens), e.celula)


def _itens_contexto(d: DadosAtendimento) -> Dict[str, List[str]]:
    c = d.contexto
    alerg = []
    for a in c.alergias:
        extra = []
        if a["gravidade"]:
            extra.append(GRAVIDADE.get(a["gravidade"], a["gravidade"]))
        mani = sorted({MANIFESTACAO.get(m, m) for m, _, _ in a["reacoes"] if m})
        if mani:
            extra.append(", ".join(mani))
        if not a["confirmado"]:
            extra.append("não confirmada")
        alerg.append(a["substancia"] + (f" ({'; '.join(extra)})" if extra else ""))
    meds = []
    for m in c.medicamentos:
        # a dose costuma já estar no texto livre ("Losartana 50 mg"): não repete
        det = ", ".join(x for x in [m["dose"] if m["dose"] and m["dose"] not in m["descricao"] else None,
                                    m["frequencia"]] if x)
        meds.append(m["descricao"] + (f" - {det}" if det else "") + (f" (desde {fmt_data(m['desde'])})" if m["desde"] else ""))
    doen = [f"{x['descricao']} ({x['codigo']}; {'ativa' if x['status'] == 'ativa' else 'em remissão'})" for x in c.doencas]
    tipo = [f"{c.tipo_sanguineo['valor']} (registrado em {fmt_data(c.tipo_sanguineo['registrado_em'])})"] if c.tipo_sanguineo else []
    return {"alergias": alerg, "medicamentos": meds, "tipo_sanguineo": tipo, "doenca_cronica": doen}


def _vitais_agrupados(d: DadosAtendimento) -> Dict[str, dict]:
    """Última medição de cada parâmetro (para resumo e evolução)."""
    ult: Dict[str, dict] = {}
    for v in d.sinais:
        ult[v["tipo"]] = v
    return ult


def vitais_resumidos(d: DadosAtendimento) -> List[Tuple[str, str, bool]]:
    """[(rótulo, valor com unidade, fora_do_limite)] na ordem clínica; PA vira 'sist/diast'."""
    ult = _vitais_agrupados(d)
    saida = []
    for tipo in VITAL_ORDEM:
        if tipo == "pa-diastolica":
            continue
        if tipo == "pa-sistolica" and ("pa-sistolica" in ult or "pa-diastolica" in ult):
            s, di = ult.get("pa-sistolica"), ult.get("pa-diastolica")
            val = f"{_fv(s['valor']) if s else '?'}/{_fv(di['valor']) if di else '?'} mmHg"
            fora = any(x and x["flag"] != "dentro-do-limite" for x in (s, di))
            saida.append(("Pressão arterial", val, fora))
        elif tipo in ult:
            v = ult[tipo]
            saida.append((VITAL_ROTULO[tipo], f"{_fv(v['valor'])} {v['unidade']}", v["flag"] != "dentro-do-limite"))
    return saida


def _grade_vitais(itens: List[Tuple[str, str, bool]], e: Estilos, t: Tema) -> Table:
    por_linha = 3 if len(itens) <= 6 else 4        # 6 sinais = 2 linhas de 3 (sem linha órfã)
    larg = LARGURA_UTIL / por_linha
    linhas, estilo = [], [("VALIGN", (0, 0), (-1, -1), "TOP"),
                          ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
    for i in range(0, len(itens), por_linha):
        fatia = itens[i:i + por_linha]
        linha = []
        for j, (rot, val, fora) in enumerate(fatia):
            linha.append([Paragraph(esc(rot), e.rotulo), Paragraph(esc(val), e.destaque),
                          Paragraph("fora do limite esperado", e.mudo) if fora else Spacer(1, 1)])
            pos = (j, len(linhas))
            estilo.append(("BOX", pos, pos, 0.6, t.borda))      # cada sinal num quadro (sem depender de cor)
            if fora:
                estilo.append(("BACKGROUND", pos, pos, t.alerta_fundo))
        linha += [""] * (por_linha - len(fatia))
        linhas.append(linha)
    tab = Table(linhas, colWidths=[larg] * por_linha)
    tab.setStyle(TableStyle(estilo))
    return tab


def _linha_atendimento(d: DadosAtendimento) -> str:
    return f"{d.rotulo} - {fmt_dt(d.inicio, d.tz)}"


# ============================================================================ DETALHADO
def story_atendimento_detalhado(d: DadosAtendimento, e: Estilos, t: Tema, com_titulo: bool = True) -> list:
    s: list = []
    if com_titulo:
        s += [P(f"Atendimento - {d.rotulo}", e.titulo_pagina),
              PM(f"Detalhado · {esc(STATUS_ATENDIMENTO.get(d.status, d.status))} · ID {esc(d.uuid)}", e.mudo)]
    if d.status == "em-andamento":
        s += [Spacer(1, 6), faixa_alerta("DOCUMENTO PARCIAL: o atendimento ainda está em andamento. Os dados "
                                          "podem mudar até a finalização.", e, t)]
    if d.status == "cancelado":
        s += [Spacer(1, 6), faixa_alerta("ATENDIMENTO CANCELADO. Motivo: "
                                          + MOTIVO_CANCELAMENTO.get(d.motivo_cancelamento, "não informado") + ".", e, t)]

    p, pr = d.paciente, d.profissional
    s += secao("Identificação", [ficha([
        ("Paciente", p["nome"]), ("Profissional", pr["nome"]),
        ("CPF", mascarar_cpf(p["cpf"]) if p["identificado"] else "-"), ("Função", pr["funcao"]),
        ("Idade / sexo", f"{p['idade']} / {p['sexo']}"), ("Registro", vazio(pr["registro"], "não informado")),
        ("Nascimento", fmt_data(p["nascimento"])), ("Tipo", d.rotulo),
        ("Peso / altura", f"{_fv(p['peso']) + ' kg' if p['peso'] else '-'} / {str(p['altura']) + ' cm' if p['altura'] else '-'}"),
        ("Status", STATUS_ATENDIMENTO.get(d.status, d.status)),
        ("Consulta", d.consulta_uuid), ("Início", fmt_dt(d.inicio, d.tz)),
        ("Atendimento", d.uuid), ("Fim / duração", f"{fmt_dt(d.fim, d.tz)} ({fmt_duracao(d.inicio, d.fim)})" if d.fim else "em andamento"),
    ], e, t)], e, t)

    s += secao("Queixa e início dos sintomas", [ficha([
        ("Queixa principal", d.queixa), ("Sintomas há",
                                         f"{d.desde_quando_sintomas} h" if d.desde_quando_sintomas is not None else "-"),
        ("Nível de consciência (AVPU)", d.avpu), ("", ""),
    ], e, t)], e, t)

    if d.sinais:
        linhas = [[VITAL_ROTULO.get(v["tipo"], humanizar(v["tipo"])) + (" (escala DPOC)" if v["dpoc"] else ""),
                   _fv(v["valor"]), v["unidade"], SITIO.get(v["sitio"], v["sitio"]), fmt_dt(v["quando"], d.tz),
                   v["por"], FLAG_FAIXA.get(v["flag"], v["flag"])] for v in d.sinais]
        fora = [i for i, v in enumerate(d.sinais) if v["flag"] != "dentro-do-limite"]
        corpo = [tabela(["Parâmetro", "Valor", "Un.", "Sítio", "Data/hora", "Coletado por", "Validação"], linhas,
                        [2.5, 0.9, 1.1, 1.5, 1.9, 2.2, 2.2], e, t, alinhar_dir=(1,), destacar=fora)]
    else:
        corpo = [P("Nenhum sinal vital registrado neste atendimento.", e.mudo)]
    s += secao("Sinais vitais", corpo, e, t)

    itens = _itens_contexto(d)
    linhas = []
    for sec, rot in SECAO_BINARIO.items():
        b = d.binario[sec]
        estado = ESTADO_BINARIO.get(b["estado"], "Pendente") if b["estado"] else "Pendente"
        if b["revisao"]:
            estado += f" ({b['revisao'].get('motivo') or 'motivo não informado'})"
        origem = {"manual": "Confirmado pelo profissional", "automatico": "Derivado do cadastro do paciente"}.get(b["origem"], "-")
        linhas.append([rot, estado, origem, _lista(itens[sec], e)])
    s += secao("Contexto clínico do paciente (conferência / binário)",
               [tabela(["Seção", "Conferência", "Origem", f"Registros vigentes em {fmt_dt(d.fim or datetime.now(timezone.utc), d.tz)}"],
                       linhas, [1.7, 1.9, 2.1, 4.6], e, t),
                P("Os registros mostram o cadastro do paciente como estava ao fim do atendimento; alterações posteriores não aparecem.", e.mudo)],
               e, t)

    if d.protocolos or d.respostas_protocolo:
        corpo = []
        if d.versoes_anteriores_input:
            corpo.append(P(f"O input foi reenviado {d.versoes_anteriores_input} vez(es); abaixo, a versão vigente (a última).", e.mudo))
        if d.respostas_protocolo:
            corpo += [Spacer(1, 3), PM("<b>Respostas do profissional ao protocolo</b>", e.corpo),
                      tabela(["Campo", "Resposta"], [[humanizar(k), v] for k, v in d.respostas_protocolo.items()],
                             [3, 5], e, t)]
        for ex in d.protocolos:
            corpo += [Spacer(1, 5), PM(f"<b>{esc(ex['nome'])}</b> · versão {esc(ex['versao'])} · "
                                       f"execução {esc(STATUS_EXEC.get(ex['status'], ex['status']))} em "
                                       f"{esc(fmt_dt(ex['executado_em'], d.tz))}"
                                       + (f" por {esc(ex['executor'])}" if ex['executor'] else ""), e.corpo),
                      PM(f"Classificação: <b>{esc(vazio(ex['classificacao']))}</b>", e.corpo)]
            if ex["trilha"]:
                corpo.append(tabela(["#", "Critério", "Valor observado", "Resultado"],
                                    [[tp.get("ordem"), tp.get("rotulo"), tp.get("valor_observado"), tp.get("peso_ou_resultado")]
                                     for tp in sorted(ex["trilha"], key=lambda x: x.get("ordem", 0))],
                                    [0.5, 3, 2.5, 2.5], e, t))
            if ex["dados_ausentes"]:
                corpo.append(P("Dados ausentes: " + ", ".join(map(str, ex["dados_ausentes"])), e.mudo))
        s += secao("Protocolo aplicado", corpo, e, t)

    if d.condutas:
        s += secao("Condutas de enfermagem", [tabela(
            ["Data/hora", "Autor", "Função", "Protocolo", "Conduta"],
            [[fmt_dt(c["quando"], d.tz), c["autor"], c["funcao"], c["protocolo"], c["descricao"]] for c in d.condutas],
            [1.8, 2, 1.2, 2, 5], e, t)], e, t)

    if d.ia:
        corpo = []
        for o in d.ia:
            corpo += [PM(f"<b>Avaliação Bion (IA)</b> · {esc(fmt_dt(o['quando'], d.tz))} · status {esc(vazio(o['status']))}"
                         f" · modelo {esc(vazio(o['modelo']))} · completude {esc(vazio(o['completude']))}"
                         f" · confiança {esc(vazio(o['confianca']))}", e.corpo)]
            if o["erro"]:
                corpo.append(P(f"Falha: {o['erro']}", e.mudo))
            if o["explicacao"]:
                corpo.append(P(o["explicacao"], e.celula))
            if o["perguntas"]:
                corpo.append(P("Perguntas pendentes: " + " | ".join(o["perguntas"]), e.mudo))
            if o["blocos"]:
                corpo.append(P("Blocos considerados: " + ", ".join(o["blocos"]), e.mudo))
            corpo.append(Spacer(1, 4))
        corpo.append(P("A IA apenas propõe; o médico que confirma é o responsável pela conduta.", e.mudo))
        s += secao("Apoio de IA", corpo, e, t)

    if d.resultados:
        corpo = []
        for r in d.resultados:
            situacao = {"confirmado": "confirmado", "rascunho": "<b>RASCUNHO (não confirmado)</b>",
                        "descartado": "<b>DESCARTADO</b>"}.get(r["status"], esc(r["status"]))
            corpo += [PM(f"<b>{esc(r['descricao'])}</b> ({esc(r['cid'])}) · {esc(CERTEZA.get(r['certeza'], r['certeza']))}"
                         f" · {esc(TIPO_PRESCRICAO.get(r['tipo'], vazio(r['tipo'])))} · {situacao}"
                         f" · origem: {esc(ORIGEM.get(r['origem'], vazio(r['origem'])))}", e.corpo)]
            partes = [f"Formulado por {vazio(r['formulado_por'])} em {fmt_dt(r['formulado_em'], d.tz)}"]
            if r["status"] == "confirmado":
                partes.append(f"confirmado em {fmt_dt(r['confirmado_em'], d.tz)}")
            if r["status"] == "descartado":
                partes.append(f"descartado em {fmt_dt(r['descartado_em'], d.tz)} por {vazio(r['descartado_por'])}")
                partes.append(f"motivo: {vazio(r['motivo_descarte'], 'não informado')}")
            if r["consistente"] is not None:
                partes.append("consistente com a classificação" if r["consistente"] else "DIVERGE da classificação do protocolo")
            hist = " | ".join(partes)
            corpo.append(P(hist, e.mudo))
            if r["medicamentos"]:
                corpo.append(tabela(["Medicamento", "Dose", "Frequência", "Duração", "Orientações", "Origem"],
                                    [[m["nome"], m["dose"], m["frequencia"], m["duracao"], m["orientacoes"],
                                      ORIGEM.get(m["origem"], m["origem"])] for m in r["medicamentos"]],
                                    [2.4, 1.3, 1.5, 1.2, 3, 1.2], e, t))
            if r["exames"]:
                corpo.append(Spacer(1, 3))
                corpo.append(tabela(["Exame", "Urgência", "Justificativa", "Origem"],
                                    [[x["nome"], URGENCIA.get(x["urgencia"], x["urgencia"]), x["justificativa"],
                                      ORIGEM.get(x["origem"], x["origem"])] for x in r["exames"]],
                                    [3, 1.3, 4, 1.3], e, t))
            corpo.append(Spacer(1, 5))
        s += secao("Diagnóstico e prescrição", corpo, e, t)

    extras = []
    if d.observacoes:
        extras.append(P(d.observacoes, e.corpo))
    if d.habitos:
        extras += [Spacer(1, 3), PM("<b>Hábitos</b>", e.corpo),
                   tabela(["Hábito", "Informação"], [[humanizar(k), v] for k, v in d.habitos.items()], [3, 5], e, t)]
    if extras:
        s += secao("Observações do profissional", extras, e, t)
    return s


# ============================================================================ RESUMO
def bloco_historico_saude(d: DadosAtendimento, e: Estilos, t: Tema) -> Table:
    """Alergias, medicamentos, doenças crônicas e tipo sanguíneo em linguagem simples (resumos)."""
    itens = _itens_contexto(d)
    linhas = []
    for sec, rot, nega in (("alergias", "Alergias", "Nega alergias"),
                           ("medicamentos", "Medicamentos em uso", "Nega uso de medicamentos"),
                           ("doenca_cronica", "Doenças crônicas", "Nega doenças crônicas"),
                           ("tipo_sanguineo", "Tipo sanguíneo", "Não coletado")):
        est = d.binario[sec]["estado"]
        if itens[sec]:
            val = _lista(itens[sec], e)
        else:
            val = P({"nega": nega, "nao-coletado": "Não coletado"}.get(est, "Sem registro"), e.celula)
        linhas.append([P(rot, e.rotulo), val])
    tab = Table(linhas, colWidths=[LARGURA_UTIL * 0.3, LARGURA_UTIL * 0.7])
    tab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.35, t.borda),
                             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return tab


def story_atendimento_resumo(d: DadosAtendimento, e: Estilos, t: Tema, com_titulo: bool = True) -> list:
    s: list = []
    p, pr = d.paciente, d.profissional
    if com_titulo:
        s += [P("Resumo do atendimento", e.titulo_pagina),
              P(f"{d.rotulo} · {data_extensa(d.inicio, d.tz)}", e.mudo), Spacer(1, 8)]
    horario = f"{fmt_hora(d.inicio, d.tz)} às {fmt_hora(d.fim, d.tz)} ({fmt_duracao(d.inicio, d.fim)})"
    s.append(cartao([
        P(p["nome"], e.destaque),
        P(f"{p['idade']} · {p['sexo']}", e.corpo), Spacer(1, 4),
        PM(f"<b>Atendido por:</b> {esc(vazio(pr['nome']))} ({esc(pr['funcao'])}"
           + (f", {esc(pr['registro'])}" if pr["registro"] else "") + ")", e.corpo),
        PM(f"<b>Quando:</b> {esc(data_extensa(d.inicio, d.tz))}, {esc(horario)}", e.corpo),
    ], t))

    if d.queixa or d.desde_quando_sintomas is not None:
        txt = vazio(d.queixa, "Não registrada")
        if d.desde_quando_sintomas is not None:
            txt += f" (sintomas há {d.desde_quando_sintomas} h)"
        s += secao("Motivo do atendimento", [P(txt, e.corpo)], e, t)

    vit = vitais_resumidos(d)
    if vit:
        s += secao("Sinais vitais", [_grade_vitais(vit, e, t)], e, t)

    tab = bloco_historico_saude(d, e, t)
    s += secao("Histórico de saúde informado", [tab], e, t)

    if d.protocolos:
        s += secao("Avaliação de risco", [P(f"{x['nome']}: {vazio(x['classificacao'], 'sem classificação')}", e.corpo)
                                           for x in d.protocolos], e, t)
    if d.condutas:
        s += secao("Cuidados realizados", [_lista([c["descricao"] for c in d.condutas], e)], e, t)

    conf = [r for r in d.resultados if r["status"] == "confirmado"]
    if conf:
        corpo = []
        for r in conf:
            corpo.append(PM(f"<b>Avaliação médica:</b> {esc(r['descricao'])} ({esc(r['cid'])}), "
                            f"{esc(CERTEZA.get(r['certeza'], r['certeza']))}", e.corpo))
            if r["medicamentos"]:
                corpo += [Spacer(1, 3), PM("<b>Medicamentos</b>", e.corpo), _lista(
                    [" - ".join(x for x in [m["nome"], ", ".join(y for y in [m["dose"], m["frequencia"], m["duracao"]] if y)] if x)
                     for m in r["medicamentos"]], e)]
            if r["exames"]:
                corpo += [Spacer(1, 3), PM("<b>Exames solicitados</b>", e.corpo),
                          _lista([x["nome"] + (f" ({URGENCIA.get(x['urgencia'], '')})" if x["urgencia"] == "urgente" or x["urgencia"] == "emergencia" else "")
                                  for x in r["exames"]], e)]
        s += secao("Diagnóstico e condutas", corpo, e, t)
    if d.observacoes:
        s += secao("Observações do profissional", [P(d.observacoes, e.corpo)], e, t)
    return s


# ============================================================================ service
def validar_modo(modo: Optional[str]) -> str:
    modo = (modo or "").strip().lower()
    if modo not in MODOS:
        raise DadosInvalidosError({"modo": f"inválido; use um de: {', '.join(MODOS)}."})
    return modo


class DownloadAtendimentoService:

    def __init__(self):
        self.repo = AtendimentoRepository()

    def gerar(self, uuid_atendimento: str, id_empresa: int, id_usuario: int, modo: str) -> Tuple[bytes, str]:
        """Devolve (bytes do PDF, nome do arquivo). Nome sem dado pessoal."""
        modo = validar_modo(modo)
        a = self.repo.find_by_uuid(uuid_atendimento, id_empresa)    # 404 igual p/ "não existe" e "outra empresa"
        if not a:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        if modo == "resumo" and a.status != "finalizado":
            raise ConflictoError("O resumo só existe para atendimento finalizado; "
                                 "use o modo 'detalhado' (parcial ou cancelado).")

        agora = datetime.now(timezone.utc)
        empresa = a.consulta.paciente.empresa
        tz = tz_empresa(empresa)
        d = montar_dados_atendimento(a, tz, agora)
        tema = TEMA_DETALHADO if modo == "detalhado" else TEMA_RESUMO
        est = estilos(tema)
        story = (story_atendimento_detalhado if modo == "detalhado" else story_atendimento_resumo)(d, est, tema)
        mold = moldura(
            empresa, f"Atendimento - {'Detalhado' if modo == 'detalhado' else 'Resumo'}", agora,
            nome_usuario_por_id(id_usuario),
            AVISO_LGPD_INTERNO if modo == "detalhado" else AVISO_RESUMO,
            marca="PARCIAL" if (modo == "detalhado" and a.status == "em-andamento") else
                  ("CANCELADO" if a.status == "cancelado" else None),
        )
        pdf = construir_pdf(story, mold, tema, titulo_meta=f"Atendimento {d.rotulo} - {modo}")
        return pdf, f"atendimento-{a.uuid[:8]}-{modo}.pdf"
