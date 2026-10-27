"""download_prescricao_service.py -- PDF da prescrição, para entregar ao PACIENTE.

Um único modo. Parte de um ResultadoPrescricao CONFIRMADO (rascunho => 409: o médico ainda não
assumiu a responsabilidade) e monta, em memória:
  - página "Receita": medicamentos (princípio ativo, dose, como usar, duração, orientações);
  - página "Solicitação de exames": só se houver exames (receita e pedido de exame costumam ser
    documentos separados, cada um com seu local de assinatura).

Deixa de fora, de propósito (decisões já tomadas): CID, qualquer menção a IA/origem da sugestão
e alergias. A responsabilidade é do médico que formulou/confirmou (`formulado_por`), não de quem
baixa o PDF.

ATENÇÃO LEGAL (confirmar com assessoria regulatória): este PDF NÃO tem assinatura digital
(ICP-Brasil ou equivalente). Por isso sai com aviso de "via informativa"; não vale como receita
eletrônica até haver integração de assinatura. Medicamento controlado/antimicrobiano tem formulário
e validade próprios e não é tratado aqui. Cobre medicamentos e exames; encaminhamento, internação e
alta não têm campos (destino, orientações, retorno) e, sozinhos, não geram PDF.

Nome, concentração e forma saem do catálogo no momento do pedido (o catálogo hoje só guarda
princípio ativo); a dose escrita pelo médico vem da própria prescrição.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

from reportlab.platypus import KeepTogether, PageBreak, Spacer, Table, TableStyle

from src.core.exceptions import ConflictoError, RecursoNaoEncontradoError
from src.core.pdf_base import (
    LARGURA_UTIL, TEMA_RESUMO, Estilos, P, PM, cartao, construir_pdf, data_curta_extensa, esc, estilos,
    faixa_alerta, fmt_hora, idade_texto,
)
from src.core.pdf_clinico import (
    attr, cidade_uf_empresa, moldura, nome_paciente, nome_usuario_por_id, registro_profissional, sexo_texto,
    tz_empresa,
)
from .download_atendimento_service import URGENCIA, dados_resultado_prescricao
from src.models.clinico import Atendimento, Consulta, ResultadoPrescricao

AVISO_SEM_ASSINATURA = ("Via informativa gerada pelo sistema, sem assinatura digital (ICP-Brasil). "
                        "Só vale como receita/pedido quando assinada pelo médico responsável.")


def _assinatura(medico, e: Estilos, t, local_data: str) -> Table:
    nome = attr(medico, "nome_completo", default="Médico responsável")
    reg = registro_profissional(medico) or "registro profissional não informado"
    tab = Table([[""], [P(nome, e.celula)], [P(reg, e.mudo)], [P(local_data, e.mudo)]],
                colWidths=[LARGURA_UTIL * 0.55])
    tab.setStyle(TableStyle([("LINEABOVE", (0, 1), (0, 1), 0.8, t.texto), ("TOPPADDING", (0, 0), (0, 0), 30),
                             ("TOPPADDING", (0, 1), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    tab.hAlign = "LEFT"
    return tab


def _cartao_paciente(d_nome: str, idade: str, sexo: str, e: Estilos, t):
    return cartao([PM(f"<b>Paciente:</b> {esc(d_nome)}", e.corpo), P(f"{idade} · {sexo}", e.mudo)], t)


def story_prescricao(r: dict, medico, paciente, empresa, tz, e: Estilos, t) -> list:
    nome = nome_paciente(paciente)
    idade = idade_texto(attr(paciente, "data_nascimento"), r["confirmado_em"])
    sexo = sexo_texto(attr(paciente, "sexo_biologico"))
    cidade = cidade_uf_empresa(empresa)
    local_data = (f"{cidade}, " if cidade else "") + data_curta_extensa(r["confirmado_em"], tz) \
        + f", {fmt_hora(r['confirmado_em'], tz)}"
    s: list = []

    if r["medicamentos"]:
        s += [P("Receita", e.titulo_pagina), P("Uso de medicamentos", e.mudo), Spacer(1, 8),
              _cartao_paciente(nome, idade, sexo, e, t), Spacer(1, 10)]
        for i, m in enumerate(r["medicamentos"], start=1):
            uso = " · ".join(x for x in [f"Como usar: {m['frequencia']}" if m["frequencia"] else None,
                                         f"Duração: {m['duracao']}" if m["duracao"] else None] if x)
            bloco = [PM(f"<b>{i}. {esc(m['nome'])}</b>" + (f" - {esc(m['dose'])}" if m["dose"] else ""), e.corpo)]
            if uso:
                bloco.append(P(uso, e.celula))
            if m["orientacoes"]:
                bloco.append(P("Orientações: " + m["orientacoes"], e.mudo))
            bloco.append(Spacer(1, 9))
            s.append(KeepTogether(bloco))
        s += [Spacer(1, 14), _assinatura(medico, e, t, local_data), Spacer(1, 10), faixa_alerta(AVISO_SEM_ASSINATURA, e, t)]

    if r["exames"]:
        if s:
            s.append(PageBreak())
        s += [P("Solicitação de exames", e.titulo_pagina), P("Pedido para realização de exames", e.mudo), Spacer(1, 8),
              _cartao_paciente(nome, idade, sexo, e, t), Spacer(1, 10)]
        for i, x in enumerate(r["exames"], start=1):
            detalhes = [f"Material: {x['material']}" if x["material"] else None,
                        f"Prioridade: {URGENCIA.get(x['urgencia'], x['urgencia'])}" if x["urgencia"] != "rotina" else None,
                        f"Jejum: {x['jejum_horas']} h" if x["jejum_horas"] else None]
            bloco = [PM(f"<b>{i}. {esc(x['nome'])}</b>", e.corpo)]
            linha = " · ".join(d for d in detalhes if d)
            if linha:
                bloco.append(P(linha, e.celula))
            if x["justificativa"]:
                bloco.append(P("Indicação: " + x["justificativa"], e.mudo))
            bloco.append(Spacer(1, 9))
            s.append(KeepTogether(bloco))
        s += [Spacer(1, 14), _assinatura(medico, e, t, local_data), Spacer(1, 10), faixa_alerta(AVISO_SEM_ASSINATURA, e, t)]
    return s


class DownloadPrescricaoService:

    def _buscar(self, uuid_resultado: str, id_empresa: int):
        """ResultadoPrescricao da empresa (404 igual p/ 'não existe' e 'é de outra empresa')."""
        r = (ResultadoPrescricao.query
             .join(Atendimento, ResultadoPrescricao.atendimento)
             .join(Consulta, Atendimento.consulta)
             .filter(ResultadoPrescricao.uuid == uuid_resultado, Consulta.id_empresa == id_empresa)
             .first())
        if not r:
            raise RecursoNaoEncontradoError(f"Prescrição não encontrada: {uuid_resultado}")
        return r

    def gerar(self, uuid_resultado: str, id_empresa: int, id_usuario: int) -> Tuple[bytes, str]:
        res = self._buscar(uuid_resultado, id_empresa)
        if res.status == "descartado":
            raise ConflictoError("Esta prescrição foi descartada e não pode ser impressa.")
        if res.status != "confirmado":
            raise ConflictoError("A prescrição ainda é um rascunho: o médico precisa confirmá-la antes de gerar o PDF.")
        r = dados_resultado_prescricao(res)
        if not r["medicamentos"] and not r["exames"]:
            raise ConflictoError("Esta conduta não tem medicamentos nem exames para imprimir.")

        agora = datetime.now(timezone.utc)
        paciente = res.atendimento.consulta.paciente
        empresa = paciente.empresa
        tz = tz_empresa(empresa)
        r["confirmado_em"] = r["confirmado_em"] or agora
        tema = TEMA_RESUMO
        est = estilos(tema)
        story = story_prescricao(r, res.usuario, paciente, empresa, tz, est, tema)
        mold = moldura(empresa, "Prescrição", agora, nome_usuario_por_id(id_usuario), AVISO_SEM_ASSINATURA)
        pdf = construir_pdf(story, mold, tema, titulo_meta="Prescrição")
        return pdf, f"prescricao-{res.uuid[:8]}.pdf"
