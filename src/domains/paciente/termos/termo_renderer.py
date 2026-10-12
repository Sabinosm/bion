"""
Monta o termo de consentimento LGPD na hora: template versionado + dados da empresa.

Colocar em src/domains/paciente/termos/termo_renderer.py
Templates em src/domains/paciente/termos/termo_<versao>.txt (ou CONSENT_TERMO_TEMPLATES).

Regras:
- Template publicado NÃO se edita: mudou o texto -> nova versão (termo_lgpd-v1.1-2026.txt).
- Jinja2 com StrictUndefined: variável faltando = erro, nunca "[CNPJ]" vazio no termo.
- A versão vira nome de arquivo: validada por regex (sem '/', '\\' ou '..').
- PDF determinístico (invariant=1): mesmo texto -> mesmos bytes -> mesmo SHA-256.
  Nome do arquivo inclui o hash, então o mesmo termo não é regravado.
- Gerar_termo devolve (texto, caminho_pdf): o texto vai para texto_termo_snapshot e o
  PDF é o que o service hasheia; os dois nascem do mesmo render, não podem divergir.
"""
import hashlib
import os
import re
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, UndefinedError
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from src.core.exceptions import DadosInvalidosError, RecursoNaoEncontradoError

_REGEX_VERSAO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
TEMPLATES_DIR = Path(os.getenv("CONSENT_TERMO_TEMPLATES", Path(__file__).resolve().parent.parent / "termos"))


# ---------------------------------------------------------------- dados da empresa
def _limpar(v) -> str:
    """Uma linha só, sem quebras: valor vindo do banco não pode criar linhas
    '## ...' ou '- ...' dentro do termo."""
    return " ".join(str(v or "").split())


def _formatar_cnpj(cnpj) -> str:
    d = re.sub(r"\D", "", cnpj or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else _limpar(cnpj)


def _logradouro(e) -> str:
    """1) coluna Empresa.logradouro (vale como correção manual, p.ex. CEP 'geral');
    2) senão, resolve pelo CEP da empresa (BrasilAPI/ViaCEP via CepService)."""
    rua = _limpar(getattr(e, "logradouro", None))
    if rua or not e.cep:
        return rua
    try:
        from src.domains.regiao.cep_service import CepService  # TODO: ajustar o caminho do import
        return _limpar(CepService().buscar_logradouro_por_cep(e.cep))
    except Exception:
        return ""   # API fora do ar: cai no erro "Faltando: logradouro" em vez de gerar termo incompleto


def _endereco(e) -> str:
    """Rua/número/bairro/CEP vêm da Empresa; cidade e UF vêm da RegiaoGeografica.
    nome_regiao só é cidade se a região for um município (tipo_regiao == 'municipio');
    se a empresa estiver ligada a uma região maior (estado, macro), usa só a UF.
    Rua: ver _logradouro (coluna da empresa ou, se vazia, o CEP)."""
    reg = e.regiao_geografica
    cidade = reg.nome_regiao if reg and reg.tipo_regiao == "municipio" else None
    uf = reg.uf if reg else None
    cidade_uf = "/".join(x for x in (_limpar(cidade), _limpar(uf)) if x)
    partes = [
        _logradouro(e), e.numero, e.complemento, e.bairro,
        cidade_uf, f"CEP {e.cep}" if e.cep else None,
    ]
    return ", ".join(p for p in (_limpar(x) for x in partes) if p)


def dados_da_empresa(empresa) -> dict:
    d = {
        "razao_social": _limpar(empresa.razao_social or empresa.nome_fantasia),
        "cnpj": _formatar_cnpj(empresa.cnpj),
        "endereco": _endereco(empresa),
        # TODO: colunas novas em Empresa (ver notas): dpo_nome, dpo_email
        "dpo_nome": _limpar(getattr(empresa, "dpo_nome", None)),
        "dpo_email": _limpar(getattr(empresa, "dpo_email", None)),
        "operador_nome": _limpar(os.getenv("OPERADOR_NOME", "Bion")),
    }
    faltando = [k for k in ("razao_social", "cnpj", "endereco", "dpo_nome", "dpo_email") if not d[k]]
    if not _logradouro(empresa):
        faltando.append("logradouro")   # sem rua, "100, Centro" não identifica a sede no termo
    if faltando:
        raise DadosInvalidosError(
            "Cadastro da empresa incompleto para gerar o termo. Faltando: " + ", ".join(faltando)
        )
    return d


# ---------------------------------------------------------------- render
def renderizar_texto(versao: str, empresa, escopos: dict) -> str:
    if not _REGEX_VERSAO.match(versao or ""):
        raise DadosInvalidosError("Versão do termo inválida.")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined, autoescape=False,
        trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
    )
    try:
        tpl = env.get_template(f"termo_{versao}.txt")
        texto = tpl.render(versao=versao, escopos=escopos, **dados_da_empresa(empresa))
    except TemplateNotFound:
        raise RecursoNaoEncontradoError(f"Versão de termo inexistente: {versao}")
    except UndefinedError as ex:
        raise DadosInvalidosError(f"Template do termo usa variável desconhecida: {ex.message}")
    return texto


def gerar_pdf_bytes(texto: str) -> bytes:
    base = dict(fontName="Helvetica", fontSize=10, leading=14)
    st = {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=14, leading=18, spaceAfter=4),
        "sub": ParagraphStyle("sub", fontName="Helvetica-Oblique", fontSize=9, leading=12, spaceAfter=10),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=10, spaceAfter=3),
        "p": ParagraphStyle("p", spaceAfter=5, **base),
        "li": ParagraphStyle("li", **base),
    }
    story, itens, apos_h1 = [], [], False

    def fechar_lista():
        nonlocal itens
        if itens:
            story.append(ListFlowable(itens, bulletType="bullet", start="-", leftIndent=14))
            story.append(Spacer(1, 4))
            itens = []

    for linha in texto.splitlines():
        linha = linha.rstrip()
        if not linha:
            continue
        if linha.startswith("- "):
            itens.append(ListItem(Paragraph(escape(linha[2:]), st["li"])))
            continue
        fechar_lista()
        if linha.startswith("## "):
            story.append(Paragraph(escape(linha[3:]), st["h2"]))
        elif linha.startswith("# "):
            story.append(Paragraph(escape(linha[2:]), st["h1"]))
            apos_h1 = True
        elif apos_h1:
            story.append(Paragraph(escape(linha), st["sub"]))
            apos_h1 = False
        else:
            story.append(Paragraph(escape(linha), st["p"]))
    fechar_lista()

    buf = BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
        bottomMargin=20 * mm, title="Termo de Consentimento LGPD", author="", invariant=1,
    ).build(story)
    return buf.getvalue()


def gerar_termo(versao: str, empresa, escopos: dict, destino: Path):
    """Retorna (texto, caminho_do_pdf). Idempotente: mesmo conteúdo = mesmo arquivo."""
    texto = renderizar_texto(versao, empresa, escopos)
    pdf = gerar_pdf_bytes(texto)
    h = hashlib.sha256(pdf).hexdigest()
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{versao}-emp{empresa.id}-{h[:12]}.pdf"
    if not caminho.exists():
        tmp = caminho.with_suffix(".tmp")
        tmp.write_bytes(pdf)
        os.replace(tmp, caminho)     # atômico: nunca fica PDF pela metade
    return texto, caminho