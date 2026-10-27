"""pdf_base.py -- camada visual e de formatação compartilhada pelos PDFs de download.

Usada por download_atendimento_service, download_consulta_service e
download_prescricao_service. Aqui não há regra clínica nem acesso a banco: só
layout (cabeçalho, rodapé, paginação, tabelas, estilos) e formatação (datas no
fuso da empresa, idade, duração, CPF mascarado).

Todo texto vindo do banco passa por `P()`, que escapa o markup do Paragraph:
observação com "<" ou "&" não quebra o PDF. `PM()` é o único que aceita markup
(só para texto escrito no código).

Dois temas:
  TEMA_DETALHADO -- cinza neutro, fonte menor, mais informação por página (auditoria/estudo).
  TEMA_RESUMO    -- azul-petróleo, mais espaço, cartões (apresentável; também a prescrição).
Fonte: Helvetica (nativa do PDF, cobre o português). Evite glifos fora do WinAnsi
(por exemplo "≥"), que saem quebrados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Iterable, List, Optional, Sequence
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

TZ_PADRAO = "America/Sao_Paulo"
MARGEM_LATERAL = 16 * mm
MARGEM_TOPO = 27 * mm      # reserva o cabeçalho de página
MARGEM_BASE = 22 * mm      # reserva o rodapé de página
LARGURA_UTIL = A4[0] - 2 * MARGEM_LATERAL

_DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo")
_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro")


# --------------------------------------------------------------------------- temas
@dataclass(frozen=True)
class Tema:
    nome: str
    primaria: colors.Color
    suave: colors.Color
    borda: colors.Color
    texto: colors.Color
    mudo: colors.Color
    alerta_fundo: colors.Color
    alerta_texto: colors.Color
    corpo: float
    pequeno: float
    cartoes: bool          # True: seções em cartão colorido (resumo); False: título sóbrio


# Só preto, branco e amarelo (avisos): imprime bem em impressora monocromática. Nada de cinza em
# texto ou fundo; hierarquia vem de negrito, itálico, tamanho e linhas. O amarelo só marca aviso.
PRETO = colors.black
AMARELO = colors.HexColor("#FFE600")

TEMA_DETALHADO = Tema(
    nome="detalhado", primaria=PRETO, suave=colors.white, borda=PRETO, texto=PRETO, mudo=PRETO,
    alerta_fundo=AMARELO, alerta_texto=PRETO, corpo=8.6, pequeno=7.2, cartoes=False,
)
TEMA_RESUMO = Tema(
    nome="resumo", primaria=PRETO, suave=colors.white, borda=PRETO, texto=PRETO, mudo=PRETO,
    alerta_fundo=AMARELO, alerta_texto=PRETO, corpo=10.0, pequeno=8.0, cartoes=True,
)


@dataclass
class Estilos:
    """Estilos de parágrafo já ligados ao tema (criados por `estilos(tema)`)."""
    corpo: ParagraphStyle
    pequeno: ParagraphStyle
    mudo: ParagraphStyle
    rotulo: ParagraphStyle
    secao: ParagraphStyle
    subsecao: ParagraphStyle
    cab_tabela: ParagraphStyle
    celula: ParagraphStyle
    celula_dir: ParagraphStyle
    destaque: ParagraphStyle
    titulo_pagina: ParagraphStyle


def estilos(t: Tema) -> Estilos:
    base = dict(fontName="Helvetica", textColor=t.texto, leading=t.corpo * 1.3)
    corpo = ParagraphStyle("corpo", fontSize=t.corpo, **base)
    return Estilos(
        corpo=corpo,
        pequeno=ParagraphStyle("pequeno", parent=corpo, fontSize=t.pequeno, leading=t.pequeno * 1.3),
        mudo=ParagraphStyle("mudo", parent=corpo, fontName="Helvetica-Oblique", fontSize=t.pequeno,
                            textColor=t.mudo, leading=t.pequeno * 1.35),
        rotulo=ParagraphStyle("rotulo", parent=corpo, fontName="Helvetica-Bold",
                              fontSize=t.pequeno - 0.4, textColor=t.mudo, leading=t.pequeno * 1.2),
        secao=ParagraphStyle("secao", parent=corpo, fontName="Helvetica-Bold",
                             fontSize=t.corpo + (2.2 if t.cartoes else 0.6),
                             textColor=t.primaria, leading=(t.corpo + 3) * 1.15),
        subsecao=ParagraphStyle("subsecao", parent=corpo, fontName="Helvetica-Bold",
                                fontSize=t.corpo + 0.4, textColor=t.primaria, spaceBefore=4,
                                spaceAfter=2),
        cab_tabela=ParagraphStyle("cab_tabela", parent=corpo, fontName="Helvetica-Bold",
                                  fontSize=t.pequeno + 0.3, textColor=colors.white,
                                  leading=(t.pequeno + 0.3) * 1.25),
        celula=ParagraphStyle("celula", parent=corpo, fontSize=t.corpo - 0.4,
                              leading=(t.corpo - 0.4) * 1.28),
        celula_dir=ParagraphStyle("celula_dir", parent=corpo, fontSize=t.corpo - 0.4,
                                  leading=(t.corpo - 0.4) * 1.28, alignment=2),
        destaque=ParagraphStyle("destaque", parent=corpo, fontName="Helvetica-Bold",
                                fontSize=t.corpo + 2, textColor=t.primaria,
                                leading=(t.corpo + 2) * 1.2),
        titulo_pagina=ParagraphStyle("titulo_pagina", parent=corpo, fontName="Helvetica-Bold",
                                     fontSize=t.corpo + 8, textColor=t.primaria,
                                     leading=(t.corpo + 8) * 1.15, spaceAfter=2),
    )


# --------------------------------------------------------------------- texto/markup
def esc(texto) -> str:
    """Escapa texto do banco para uso dentro de Paragraph; quebra de linha vira <br/>."""
    if texto is None:
        return ""
    return escape(str(texto)).replace("\r\n", "\n").replace("\n", "<br/>")


def P(texto, estilo: ParagraphStyle) -> Paragraph:
    """Parágrafo com texto do banco (escapado)."""
    return Paragraph(esc(texto), estilo)


def PM(markup: str, estilo: ParagraphStyle) -> Paragraph:
    """Parágrafo com markup ESCRITO NO CÓDIGO (<b>, <font>...). Valores do banco entram por esc()."""
    return Paragraph(markup, estilo)


def vazio(texto, alternativa: str = "-") -> str:
    """Texto ou travessão: células nunca ficam em branco sem explicação."""
    t = "" if texto is None else str(texto).strip()
    return t if t else alternativa


_SIGLAS = {"spo2": "SpO2", "o2": "O2", "pa": "PA", "avpu": "AVPU", "cid": "CID", "dpoc": "DPOC",
           "fc": "FC", "fr": "FR", "tax": "TAX"}


def humanizar(chave: str) -> str:
    """'usa_o2' -> 'Usa O2' (fallback quando não há rótulo; chaves sem acento ficam sem acento)."""
    palavras = str(chave).replace("_", " ").replace("-", " ").strip().split()
    palavras = [_SIGLAS.get(w.lower(), w) for w in palavras]
    s = " ".join(palavras)
    return s[:1].upper() + s[1:]


# ----------------------------------------------------------------- datas/formatação
def como_tz(fuso) -> ZoneInfo:
    """Aceita nome de fuso, ZoneInfo ou None (cai em America/Sao_Paulo)."""
    if isinstance(fuso, ZoneInfo):
        return fuso
    try:
        return ZoneInfo(str(fuso)) if fuso else ZoneInfo(TZ_PADRAO)
    except Exception:
        return ZoneInfo(TZ_PADRAO)


def como_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MySQL costuma devolver datetime sem fuso: assume UTC (é como o app grava)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def fmt_dt(dt: Optional[datetime], fuso=None) -> str:
    dt = como_utc(dt)
    return dt.astimezone(como_tz(fuso)).strftime("%d/%m/%Y %H:%M") if dt else "-"


def fmt_hora(dt: Optional[datetime], fuso=None) -> str:
    dt = como_utc(dt)
    return dt.astimezone(como_tz(fuso)).strftime("%H:%M") if dt else "-"


def fmt_data(d) -> str:
    if d is None:
        return "-"
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y")
    return d.strftime("%d/%m/%Y") if isinstance(d, date) else str(d)


def data_extensa(dt: datetime, fuso=None) -> str:
    """'segunda-feira, 26 de outubro de 2026' (sem depender de locale do servidor)."""
    l = como_utc(dt).astimezone(como_tz(fuso))
    return f"{_DIAS[l.weekday()]}, {l.day} de {_MESES[l.month - 1]} de {l.year}"


def data_curta_extensa(dt: datetime, fuso=None) -> str:
    """'26 de outubro de 2026'."""
    l = como_utc(dt).astimezone(como_tz(fuso))
    return f"{l.day} de {_MESES[l.month - 1]} de {l.year}"


def emitido_em_texto(agora: datetime, fuso=None) -> str:
    """'segunda-feira, 26 de outubro de 2026, às 17:35 (horário de Brasília)'."""
    tz = como_tz(fuso)
    hora = como_utc(agora).astimezone(tz).strftime("%H:%M")
    sufixo = " (horário de Brasília)" if tz.key == TZ_PADRAO else f" ({tz.key})"
    return f"{data_extensa(agora, tz)}, às {hora}{sufixo}"


def idade_texto(nascimento: Optional[date], ref: Optional[datetime] = None) -> str:
    if not nascimento:
        return "idade não informada"
    hoje = (como_utc(ref) or datetime.now(timezone.utc)).date()
    meses = (hoje.year - nascimento.year) * 12 + hoje.month - nascimento.month - (hoje.day < nascimento.day)
    if meses < 0:
        return "idade não informada"
    if meses < 24:
        return f"{meses} {'mês' if meses == 1 else 'meses'}"
    return f"{meses // 12} anos"


def fmt_duracao(inicio: Optional[datetime], fim: Optional[datetime]) -> str:
    i, f = como_utc(inicio), como_utc(fim)
    if not i or not f or f < i:
        return "-"
    minutos = int((f - i).total_seconds() // 60)
    h, m = divmod(minutos, 60)
    return f"{h}h {m:02d}min" if h else f"{m} min"


def mascarar_cpf(cpf: Optional[str]) -> str:
    """***.456.789-** : identifica sem expor o CPF inteiro em documento impresso."""
    d = "".join(c for c in (cpf or "") if c.isdigit())
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else "-"


# -------------------------------------------------------------- blocos reutilizáveis
def titulo_secao(texto: str, e: Estilos, t: Tema) -> Table:
    """Título de seção: faixa suave com barra lateral (resumo) ou linha fina (detalhado)."""
    tab = Table([[Paragraph(esc(texto), e.secao)]], colWidths=[LARGURA_UTIL])
    est = [("LEFTPADDING", (0, 0), (-1, -1), 8 if t.cartoes else 0),
           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if t.cartoes:
        est += [("LINEBEFORE", (0, 0), (0, -1), 4, t.primaria), ("LINEBELOW", (0, 0), (-1, -1), 0.5, t.primaria)]
    else:
        est += [("LINEBELOW", (0, 0), (-1, -1), 0.8, t.primaria)]
    tab.setStyle(TableStyle(est))
    return tab


def secao(texto: str, conteudo: Sequence, e: Estilos, t: Tema) -> List:
    """Título + conteúdo, com respiro antes. `conteudo` é lista de flowables."""
    itens = list(conteudo)
    cabeca = [titulo_secao(texto, e, t), Spacer(1, 4)] + itens[:1]
    # o título nunca fica sozinho no fim da página: vai junto com o primeiro bloco
    return [Spacer(1, 9 if t.cartoes else 7), KeepTogether(cabeca), *itens[1:]]


def tabela(cabecalho: Sequence[str], linhas: Iterable[Sequence], larguras: Sequence[float],
           e: Estilos, t: Tema, alinhar_dir: Sequence[int] = (), destacar: Sequence[int] = ()) -> Table:
    """Tabela com cabeçalho repetido nas quebras de página e linhas zebradas.

    `linhas`: células em texto (escapado aqui) ou Flowable pronto.
    `larguras`: proporções (somam o que quiser); normalizadas para a largura útil.
    `destacar`: índices das linhas (0 = primeira linha de dados) com fundo de alerta.
    """
    soma = float(sum(larguras))
    cols = [LARGURA_UTIL * w / soma for w in larguras]
    dados = [[Paragraph(esc(c), e.cab_tabela) for c in cabecalho]]
    for linha in linhas:
        dados.append([
            c if hasattr(c, "wrap") else Paragraph(esc(vazio(c)), e.celula_dir if i in alinhar_dir else e.celula)
            for i, c in enumerate(linha)
        ])
    tab = Table(dados, colWidths=cols, repeatRows=1)
    est = [
        ("BACKGROUND", (0, 0), (-1, 0), t.primaria),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, t.borda),
        ("BOX", (0, 0), (-1, -1), 0.7, t.borda),
    ]
    for n in range(1, len(dados)):
        if n % 2 == 0:
            est.append(("BACKGROUND", (0, n), (-1, n), t.suave))
    for idx in destacar:
        est.append(("BACKGROUND", (0, idx + 1), (-1, idx + 1), t.alerta_fundo))
    tab.setStyle(TableStyle(est))
    return tab


def ficha(pares: Sequence[tuple], e: Estilos, t: Tema, colunas: int = 2) -> Table:
    """Grade de 'rótulo / valor' (identificação). `pares`: [(rótulo, valor), ...]."""
    larg_rot, larg_val = 0.34, 0.66
    por_col = LARGURA_UTIL / colunas
    cols = []
    for _ in range(colunas):
        cols += [por_col * larg_rot, por_col * larg_val]
    linhas = []
    for i in range(0, len(pares), colunas):
        fatia = list(pares[i:i + colunas])
        linha = []
        for rot, val in fatia:
            if not rot and not val:
                linha += ["", ""]
            else:
                linha += [Paragraph(esc(rot), e.rotulo), Paragraph(esc(vazio(val)), e.celula)]
        while len(linha) < colunas * 2:
            linha += ["", ""]
        linhas.append(linha)
    tab = Table(linhas, colWidths=cols)
    est = [("VALIGN", (0, 0), (-1, -1), "TOP"),
           ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
           ("LINEBELOW", (0, 0), (-1, -1), 0.3, t.borda)]
    if t.cartoes:
        est += [("BOX", (0, 0), (-1, -1), 0.7, t.borda), ("BACKGROUND", (0, 0), (-1, -1), colors.white)]
    tab.setStyle(TableStyle(est))
    return tab


def faixa_alerta(texto: str, e: Estilos, t: Tema) -> Table:
    """Caixa âmbar para avisos (parcial, sem assinatura, cancelado...)."""
    tab = Table([[Paragraph(esc(texto), e.celula)]], colWidths=[LARGURA_UTIL])
    tab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), t.alerta_fundo), ("BOX", (0, 0), (-1, -1), 0.7, t.alerta_texto),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return tab


def cartao(flowables: Sequence, t: Tema, largura: float = LARGURA_UTIL) -> Table:
    """Envolve flowables num cartão com borda e fundo suave (usado no resumo)."""
    tab = Table([[list(flowables)]], colWidths=[largura])
    tab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), t.suave), ("BOX", (0, 0), (-1, -1), 0.7, t.borda),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return tab


# ------------------------------------------------------------------ documento/moldura
@dataclass
class Moldura:
    """O que aparece no cabeçalho e no rodapé de TODAS as páginas."""
    empresa_nome: str
    empresa_linha: str = ""          # ex.: "CNPJ 00.000.000/0001-00 · CNES 1234567"
    titulo: str = ""                 # ex.: "Atendimento - Detalhado"
    emitido_em: str = ""             # já formatado (data_extensa + hora)
    emitido_por: Optional[str] = None
    aviso_rodape: str = ""
    marca_dagua: Optional[str] = None   # etiqueta no cabeçalho de toda página, ex.: "PARCIAL"
    extra_rodape: List[str] = field(default_factory=list)


def _desenhar_moldura(c: rl_canvas.Canvas, m: Moldura, t: Tema, pagina: int, total: int) -> None:
    larg, alt = A4
    c.saveState()
    # --- cabeçalho
    c.setFillColor(t.primaria)
    c.rect(0, alt - 6 * mm, larg, 6 * mm, stroke=0, fill=1)
    c.setFillColor(t.texto)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGEM_LATERAL, alt - 13.2 * mm, m.empresa_nome[:70])
    c.setFont("Helvetica", 7.4)
    c.setFillColor(t.mudo)
    if m.empresa_linha:
        c.drawString(MARGEM_LATERAL, alt - 17.4 * mm, m.empresa_linha[:110])
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(t.primaria)
    c.drawRightString(larg - MARGEM_LATERAL, alt - 13.2 * mm, m.titulo)
    if m.marca_dagua:
        # etiqueta preta com texto branco (legível em impressão monocromática; não cobre dado)
        c.setFont("Helvetica-Bold", 8.5)
        w = c.stringWidth(m.marca_dagua, "Helvetica-Bold", 8.5) + 10
        c.setFillColor(colors.black)
        c.rect(larg - MARGEM_LATERAL - w, alt - 18.9 * mm, w, 4.6 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.drawCentredString(larg - MARGEM_LATERAL - w / 2, alt - 17.5 * mm, m.marca_dagua)
    c.setStrokeColor(t.borda)
    c.setLineWidth(0.6)
    c.line(MARGEM_LATERAL, alt - 20.5 * mm, larg - MARGEM_LATERAL, alt - 20.5 * mm)
    # --- rodapé
    c.line(MARGEM_LATERAL, 17 * mm, larg - MARGEM_LATERAL, 17 * mm)
    c.setFont("Helvetica", 6.9)
    c.setFillColor(t.mudo)
    y = 13.7 * mm
    linhas = []
    if m.emitido_em:
        quem = f" por {m.emitido_por}" if m.emitido_por else ""
        linhas.append(f"Emitido em {m.emitido_em}{quem}.")
    linhas += [l for l in [m.aviso_rodape, *m.extra_rodape] if l]
    largura_texto = larg - 2 * MARGEM_LATERAL - 24 * mm      # sobra espaço p/ "Página x de y"
    quebradas = [parte for ln in linhas for parte in simpleSplit(ln, "Helvetica", 6.9, largura_texto)]
    for ln in quebradas[:4]:
        c.drawString(MARGEM_LATERAL, y, ln)
        y -= 3.1 * mm
    c.setFont("Helvetica-Bold", 7.6)
    c.drawRightString(larg - MARGEM_LATERAL, 13.6 * mm, f"Página {pagina} de {total}")
    c.restoreState()


def _canvas_numerado(m: Moldura, t: Tema):
    class _Canvas(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._estados: list = []

        def showPage(self):
            self._estados.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._estados)
            for estado in self._estados:
                self.__dict__.update(estado)
                _desenhar_moldura(self, m, t, self._pageNumber, total)
                super().showPage()
            super().save()
    return _Canvas


def construir_pdf(story: Sequence, moldura: Moldura, tema: Tema, titulo_meta: str = "") -> bytes:
    """Renderiza a história em memória e devolve os bytes (nada vai a disco)."""
    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=MARGEM_LATERAL, rightMargin=MARGEM_LATERAL,
        topMargin=MARGEM_TOPO, bottomMargin=MARGEM_BASE,
        title=titulo_meta or moldura.titulo, author=moldura.empresa_nome, creator="Bion",
    )
    quadro = Frame(MARGEM_LATERAL, MARGEM_BASE, LARGURA_UTIL, A4[1] - MARGEM_TOPO - MARGEM_BASE,
                   leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="corpo")
    doc.addPageTemplates([PageTemplate(id="p", frames=[quadro])])
    doc.build(list(story), canvasmaker=_canvas_numerado(moldura, tema))
    return buf.getvalue()
