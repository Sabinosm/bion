"""download_consulta_service.py -- PDF de uma Consulta (o episódio inteiro), em dois modos.

  detalhado -- auditoria/estudo: ficha do episódio, consentimento LGPD, linha do tempo com TODOS
               os atendimentos (inclusive cancelados), tempos, evolução dos sinais vitais e das
               classificações, diagnóstico/prescrição finais, desfecho e, em anexo, o detalhado
               de cada atendimento (o mesmo do download_atendimento_service).
  resumo    -- 1 a 2 páginas, apresentável e seguro para o paciente: linha do tempo compacta (sem
               atendimentos cancelados), primeira x última medição, risco inicial e final,
               diagnóstico e condutas finais, desfecho.

Consulta ainda aberta: os dois modos saem, com a marca PARCIAL e um aviso (diferente do
Atendimento, aqui o resumo parcial é útil: o paciente pode precisar dele antes da alta).
Montado em memória, sem auditoria, com data/dia/hora e quem emitiu (mesma lógica do atendimento).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from reportlab.platypus import PageBreak, Spacer

from src.core.exceptions import RecursoNaoEncontradoError
from src.core.pdf_base import (
    TEMA_DETALHADO, TEMA_RESUMO, Estilos, P, PM, cartao, como_utc, construir_pdf, data_extensa, esc, estilos,
    faixa_alerta, ficha, fmt_dt, fmt_duracao, fmt_hora, secao, tabela, vazio,
)
from src.core.pdf_clinico import (
    AVISO_LGPD_INTERNO, AVISO_RESUMO, attr, moldura, nome_usuario_por_id, tz_empresa,
)
from .download_atendimento_service import (
    CERTEZA, STATUS_ATENDIMENTO, URGENCIA, DadosAtendimento, _lista, bloco_historico_saude,
    dados_paciente, montar_dados_atendimento, story_atendimento_detalhado, validar_modo, vitais_resumidos,
)
from src.domains.consulta.service import ConsultaService

STATUS_CONSULTA = {"aguardando-triagem": "Aguardando triagem", "em-triagem": "Em triagem",
                   "aguardando-medico": "Aguardando médico", "em-atendimento": "Em atendimento",
                   "em-observacao": "Em observação", "encerrada": "Encerrada"}
DESFECHO = {"alta": "Alta", "internacao": "Internação", "transferencia": "Transferência", "obito": "Óbito",
            "evasao": "Evasão"}
ORIGEM_ENCAMINHAMENTO = {"espontanea": "Espontânea", "SAMU": "SAMU", "transferencia": "Transferência",
                         "regulacao": "Regulação"}
SITUACAO_CONSENTIMENTO = {"ativo": "Termo LGPD assinado/ativo", "dispensado_emergencia": "Dispensado por emergência",
                          None: "Pendente (sem registro)"}
CANAL = {"presencial-papel": "presencial (papel)", "presencial-digital": "presencial (digital)",
         "portal-online": "portal online", "totem": "totem", "dispensa-emergencia": "dispensa por emergência"}


# ============================================================================ dados
@dataclass
class DadosConsulta:
    uuid: str
    status: str
    origem: Optional[str]
    inicio: Optional[datetime]
    fim: Optional[datetime]
    desfecho: Optional[str]
    iniciada_por: Optional[str]
    finalizada_por: Optional[str]
    paciente: Dict
    tz: object
    consentimento: Dict = field(default_factory=dict)
    atendimentos: List[DadosAtendimento] = field(default_factory=list)

    @property
    def encerrada(self) -> bool:
        return self.status == "encerrada"

    def validos(self) -> List[DadosAtendimento]:
        """Atendimentos que não foram cancelados."""
        return [a for a in self.atendimentos if a.status != "cancelado"]

    def tempo_ate(self, tipos: Tuple[str, ...]) -> str:
        """Do início da consulta ao início do 1º atendimento dos `tipos` (não cancelado)."""
        for a in self.validos():
            if a.tipo in tipos:
                return fmt_duracao(self.inicio, a.inicio)
        return "-"


def _consentimento(consulta, id_empresa: int, svc: ConsultaService) -> Dict:
    """Situação válida p/ esta consulta ('ativo' | 'dispensado_emergencia' | None) + o registro que a sustenta."""
    situacao = svc.situacao_consentimento(consulta.uuid, id_empresa).get("situacao")
    candidatos = [c for c in (getattr(consulta.paciente, "consentimentos", None) or []) if situacao and c.status == situacao]
    reg = max(candidatos, key=lambda c: como_utc(c.data_consentimento)) if candidatos else None
    return {"situacao": situacao, "registro": reg.to_dict() if reg else None,
            "data": reg.data_consentimento if reg else None}


def montar_dados_consulta(consulta, id_empresa: int, tz, agora: datetime, svc: ConsultaService) -> DadosConsulta:
    pac = consulta.paciente
    d = DadosConsulta(
        uuid=consulta.uuid, status=consulta.status_consulta, origem=consulta.origem_encaminhamento,
        inicio=consulta.data_hora_inicio, fim=consulta.data_hora_fim, desfecho=consulta.desfecho_final,
        iniciada_por=attr(consulta.usuario_iniciou, "nome_completo"),
        finalizada_por=attr(consulta.usuario_finalizou, "nome_completo"),
        paciente=dados_paciente(pac, consulta.data_hora_fim or agora), tz=tz,
        consentimento=_consentimento(consulta, id_empresa, svc),
    )
    ordenados = sorted(consulta.atendimentos or [], key=lambda a: (como_utc(a.data_hora_inicio), a.id))
    d.atendimentos = [montar_dados_atendimento(a, tz, agora) for a in ordenados]
    return d


# ======================================================================= blocos comuns
def _ficha_episodio(d: DadosConsulta, e: Estilos, t) -> list:
    return [ficha([
        ("Origem", ORIGEM_ENCAMINHAMENTO.get(d.origem, d.origem)), ("Status", STATUS_CONSULTA.get(d.status, d.status)),
        ("Início", fmt_dt(d.inicio, d.tz)), ("Encerramento", fmt_dt(d.fim, d.tz) if d.fim else "em aberto"),
        ("Duração total", fmt_duracao(d.inicio, d.fim) if d.fim else "-"), ("Desfecho", DESFECHO.get(d.desfecho, "-")),
        ("Aberta por", d.iniciada_por), ("Encerrada por", d.finalizada_por),
    ], e, t)]


def _matriz_vitais(d: DadosConsulta, e: Estilos, t, apenas_extremos: bool):
    """Parâmetros x atendimentos (última medição de cada atendimento). Resumo: 1ª e última coluna."""
    cols = [(a, {r: (v, fora) for r, v, fora in vitais_resumidos(a)}) for a in d.validos()]
    cols = [(a, m) for a, m in cols if m]
    if not cols:
        return None
    if apenas_extremos and len(cols) > 2:
        cols = [cols[0], cols[-1]]
    cols = cols[:7]
    rotulos = []
    for _, m in cols:
        for r in m:
            if r not in rotulos:
                rotulos.append(r)
    cab = ["Parâmetro"] + [f"{a.rotulo}\n{fmt_dt(a.inicio, d.tz)}" for a, _ in cols]
    linhas = []
    for i, r in enumerate(rotulos):
        linha = [r]
        for _, m in cols:
            v = m.get(r)
            linha.append(f"{v[0]}{'  (!)' if v and v[1] else ''}" if v else "-")
        linhas.append(linha)
    return tabela(cab, linhas, [2.4] + [1.7] * len(cols), e, t, alinhar_dir=tuple(range(1, len(cols) + 1)))


def _ultimo_confirmado(d: DadosConsulta) -> Optional[Tuple[DadosAtendimento, dict]]:
    for a in reversed(d.validos()):
        conf = [r for r in a.resultados if r["status"] == "confirmado"]
        if conf:
            return a, conf[-1]
    return None


def _bloco_conduta_final(r: dict, e: Estilos, incluir_cid: bool = True) -> list:
    corpo = [PM(f"<b>{esc(r['descricao'])}</b>" + (f" ({esc(r['cid'])})" if incluir_cid else "")
                + f", {esc(CERTEZA.get(r['certeza'], r['certeza']))}", e.corpo)]
    if r["medicamentos"]:
        corpo += [Spacer(1, 3), PM("<b>Medicamentos</b>", e.corpo), _lista(
            [" - ".join(x for x in [m["nome"], ", ".join(y for y in [m["dose"], m["frequencia"], m["duracao"]] if y)] if x)
             for m in r["medicamentos"]], e)]
    if r["exames"]:
        corpo += [Spacer(1, 3), PM("<b>Exames solicitados</b>", e.corpo), _lista(
            [x["nome"] + (f" ({URGENCIA[x['urgencia']].lower()})" if x["urgencia"] in ("urgente", "emergencia") else "")
             for x in r["exames"]], e)]
    return corpo


# ============================================================================ DETALHADO
def story_consulta_detalhado(d: DadosConsulta, e: Estilos, t) -> list:
    p = d.paciente
    s: list = [P("Consulta - Detalhado", e.titulo_pagina), P(f"ID {d.uuid} · {p['nome']} · {p['idade']} · {p['sexo']}", e.mudo)]
    if not d.encerrada:
        s += [Spacer(1, 6), faixa_alerta("DOCUMENTO PARCIAL: a consulta ainda está aberta "
                                          f"({STATUS_CONSULTA.get(d.status, d.status)}). Os dados podem mudar até o encerramento.", e, t)]

    s += secao("Episódio", _ficha_episodio(d, e, t), e, t)

    c = d.consentimento
    reg = c.get("registro") or {}
    linhas = [("Situação", SITUACAO_CONSENTIMENTO.get(c.get("situacao"), c.get("situacao"))),
              ("Versão do termo", reg.get("versao_termo")), ("Canal", CANAL.get(reg.get("canal_coleta"), reg.get("canal_coleta"))),
              ("Registrado em", fmt_dt(c.get("data"), d.tz)),
              ("Escopos aceitos", ", ".join(reg.get("escopos_aceitos") or []) or "nenhum"),
              ("Escopos recusados", ", ".join(reg["escopos_recusados"]) if reg.get("escopos_recusados") else
               ("não informado" if reg.get("escopos_recusados") is None and reg else "nenhum")),
              ("Observação", reg.get("observacao")), ("", "")]
    s += secao("Consentimento LGPD", [ficha(linhas, e, t)], e, t)

    if d.atendimentos:
        linhas = [[i + 1, a.rotulo, a.profissional["nome"], fmt_dt(a.inicio, d.tz), fmt_dt(a.fim, d.tz),
                   fmt_duracao(a.inicio, a.fim), STATUS_ATENDIMENTO.get(a.status, a.status)]
                  for i, a in enumerate(d.atendimentos)]
        canc = [i for i, a in enumerate(d.atendimentos) if a.status == "cancelado"]
        corpo = [tabela(["#", "Tipo", "Profissional", "Início", "Fim", "Duração", "Status"], linhas,
                        [0.5, 2, 2.7, 2, 2, 1.3, 1.6], e, t, destacar=canc)]
    else:
        corpo = [P("Nenhum atendimento registrado nesta consulta.", e.mudo)]
    s += secao("Linha do tempo dos atendimentos", corpo, e, t)

    s += secao("Tempos", [ficha([
        ("Chegada até a triagem", d.tempo_ate(("triagem",))),
        ("Chegada até o médico", d.tempo_ate(("avaliacao-medica", "reavaliacao"))),
        ("Duração total", fmt_duracao(d.inicio, d.fim) if d.fim else "em aberto"), ("", ""),
    ], e, t)], e, t)

    m = _matriz_vitais(d, e, t, apenas_extremos=False)
    if m is not None:
        s += secao("Evolução dos sinais vitais", [m, P("(!) = fora do limite esperado. Última medição de cada atendimento.", e.mudo)], e, t)

    prot = [[f"{a.rotulo} - {fmt_dt(a.inicio, d.tz)}", x["nome"], x["classificacao"]] for a in d.validos() for x in a.protocolos]
    if prot:
        s += secao("Evolução da classificação (protocolos)", [tabela(["Atendimento", "Protocolo", "Classificação"], prot, [3, 2.5, 3], e, t)], e, t)

    fin = _ultimo_confirmado(d)
    if fin:
        a, r = fin
        s += secao("Diagnóstico e conduta finais",
                   [P(f"Confirmado por {vazio(r['formulado_por'])} em {fmt_dt(r['confirmado_em'], d.tz)} ({a.rotulo}).", e.mudo),
                    *_bloco_conduta_final(r, e)], e, t)

    s += secao("Desfecho", [ficha([("Desfecho", DESFECHO.get(d.desfecho, "ainda não definido")),
                                    ("Encerrada por", d.finalizada_por)], e, t)], e, t)

    for i, a in enumerate(d.atendimentos, start=1):
        s += [PageBreak(), P(f"Anexo {i} de {len(d.atendimentos)} - {a.rotulo}", e.titulo_pagina),
              PM(f"{esc(STATUS_ATENDIMENTO.get(a.status, a.status))} · {esc(fmt_dt(a.inicio, d.tz))} · ID {esc(a.uuid)}", e.mudo)]
        s += story_atendimento_detalhado(a, e, t, com_titulo=False)
    return s


# ============================================================================ RESUMO
def story_consulta_resumo(d: DadosConsulta, e: Estilos, t) -> list:
    p = d.paciente
    s: list = [P("Resumo da consulta", e.titulo_pagina),
               P(f"{data_extensa(d.inicio, d.tz)}", e.mudo), Spacer(1, 8)]
    if not d.encerrada:
        s += [faixa_alerta(f"Consulta em andamento ({STATUS_CONSULTA.get(d.status, d.status).lower()}): "
                           "este resumo é parcial e pode mudar até o encerramento.", e, t), Spacer(1, 6)]
    s.append(cartao([P(p["nome"], e.destaque), P(f"{p['idade']} · {p['sexo']}", e.corpo), Spacer(1, 4),
                     PM(f"<b>Início:</b> {esc(fmt_dt(d.inicio, d.tz))} &nbsp;&nbsp; "
                        + (f"<b>Encerramento:</b> {esc(fmt_dt(d.fim, d.tz))} ({esc(fmt_duracao(d.inicio, d.fim))})" if d.fim
                           else "<b>Encerramento:</b> em aberto"), e.corpo)], t))

    validos = d.validos()
    if validos:
        linhas = [[a.rotulo, a.profissional["nome"] + (f" ({a.profissional['funcao']})" if a.profissional["funcao"] else ""),
                   f"{fmt_hora(a.inicio, d.tz)} - {fmt_hora(a.fim, d.tz)}" if a.fim else f"{fmt_hora(a.inicio, d.tz)} - em andamento"]
                  for a in validos]
        s += secao("Atendimentos", [tabela(["Etapa", "Profissional", "Horário"], linhas, [2.2, 4.5, 2.3], e, t)], e, t)

    m = _matriz_vitais(d, e, t, apenas_extremos=True)
    if m is not None:
        s += secao("Sinais vitais", [m, P("(!) = fora do limite esperado.", e.mudo)], e, t)

    prot = [(a, x) for a in validos for x in a.protocolos if x["classificacao"]]
    if prot:
        ini, fim = prot[0], prot[-1]
        txt = f"{ini[1]['nome']}: {ini[1]['classificacao']}" + (
            f" (inicial), depois {fim[1]['classificacao']} (final)" if fim is not ini and fim[1]["classificacao"] != ini[1]["classificacao"] else "")
        s += secao("Avaliação de risco", [P(txt, e.corpo)], e, t)

    if validos:
        s += secao("Histórico de saúde informado", [bloco_historico_saude(validos[-1], e, t)], e, t)

    fin = _ultimo_confirmado(d)
    if fin:
        s += secao("Diagnóstico e condutas", _bloco_conduta_final(fin[1], e), e, t)

    s += secao("Desfecho", [P(DESFECHO.get(d.desfecho, "Ainda não definido (consulta em andamento)."), e.corpo)], e, t)
    return s


# ============================================================================ service
class DownloadConsultaService:

    def __init__(self):
        self.consulta_svc = ConsultaService()

    def gerar(self, uuid_consulta: str, id_empresa: int, id_usuario: int, modo: str) -> Tuple[bytes, str]:
        modo = validar_modo(modo)
        c = self.consulta_svc.buscar_por_uuid(uuid_consulta, id_empresa)     # 404 uniforme
        if c is None:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")
        agora = datetime.now(timezone.utc)
        empresa = c.paciente.empresa
        tz = tz_empresa(empresa)
        d = montar_dados_consulta(c, id_empresa, tz, agora, self.consulta_svc)
        tema = TEMA_DETALHADO if modo == "detalhado" else TEMA_RESUMO
        est = estilos(tema)
        story = (story_consulta_detalhado if modo == "detalhado" else story_consulta_resumo)(d, est, tema)
        mold = moldura(empresa, f"Consulta - {'Detalhado' if modo == 'detalhado' else 'Resumo'}", agora,
                       nome_usuario_por_id(id_usuario), AVISO_LGPD_INTERNO if modo == "detalhado" else AVISO_RESUMO,
                       marca=None if d.encerrada else "PARCIAL")
        pdf = construir_pdf(story, mold, tema, titulo_meta=f"Consulta - {modo}")
        return pdf, f"consulta-{c.uuid[:8]}-{modo}.pdf"
