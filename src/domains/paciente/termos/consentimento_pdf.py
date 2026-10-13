"""
Monta o PDF ASSINADO do consentimento inteiramente em memória.

Colocar em src/domains/paciente/services/consentimento_pdf.py

Nada aqui toca em disco. A função é PURA e DETERMINÍSTICA: mesmos dados de
entrada => mesmos bytes (reportlab com invariant=1, sem datas "agora" dentro
do PDF; a data impressa é a data da assinatura, passada pelo chamador).
Isso permite RECONSTRUIR o PDF a qualquer momento a partir do banco e conferir
o SHA-256 contra consentimento_lgpd.hash_documento.

O hash do PDF final não aparece dentro dele (um arquivo não contém o próprio
hash). O hash do termo ORIGINAL aparece na página, ligando as duas versões.

A conferência de hash só vale enquanto reportlab, pypdf e este layout não
mudarem; se mudarem, o PDF reconstruído é equivalente no conteúdo mas terá
outro hash (o download sinaliza isso em X-Integridade).
"""
import hashlib
import re
from io import BytesIO
from typing import Iterable, Optional

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas as rl_canvas

from .termo_renderer import gerar_pdf_bytes


def formatar_cpf(cpf) -> str:
    d = re.sub(r"\D", "", cpf or "")
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else (cpf or "-")


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def montar_pdf_assinado(
    *,
    texto_termo: str,
    hash_pdf_original: str,
    nome: str,
    cpf: Optional[str],
    versao_termo: str,
    data,                                   # datetime tz-aware (UTC), sem microssegundos
    ip: Optional[str],
    user_agent: Optional[str],
    geo: Optional[str],
    assinatura_png: bytes,
    escopos_aceitos: Iterable[str] = (),
    escopos_oferecidos: Iterable[str] = (),
) -> bytes:
    """Termo original (refeito do texto) + página de comprovante com a assinatura."""
    aceitos = list(escopos_aceitos)
    oferecidos = list(escopos_oferecidos)

    try:
        from zoneinfo import ZoneInfo
        data_local = data.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S (Brasília)")
    except Exception:
        data_local = None
    data_utc = data.strftime("%d/%m/%Y %H:%M:%S UTC")

    # ---- 1) página de comprovante
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4, invariant=1)
    largura, altura = A4
    margem = 20 * mm
    largura_texto = largura - 2 * margem
    y = altura - margem

    c.setFont("Helvetica-Bold", 15)
    c.drawString(margem, y, "Comprovante de Assinatura Eletrônica")
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.drawString(margem, y, "Termo de Consentimento LGPD - Lei 13.709/2018")
    y -= 4 * mm
    c.line(margem, y, largura - margem, y)
    y -= 8 * mm

    def campo(rotulo, valor, y):
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margem, y, rotulo)
        c.setFont("Helvetica", 9)
        linhas = simpleSplit(str(valor or "-"), "Helvetica", 9, largura_texto - 45 * mm) or ["-"]
        for ln in linhas:
            c.drawString(margem + 45 * mm, y, ln)
            y -= 4.5 * mm
        return y - 1.5 * mm

    y = campo("Paciente:", nome, y)
    y = campo("CPF:", formatar_cpf(cpf), y)
    y = campo("Versão do termo:", versao_termo, y)
    y = campo("Data/hora:", f"{data_local} - {data_utc}" if data_local else data_utc, y)
    y = campo("IP:", ip, y)
    y = campo("Dispositivo:", (user_agent or "")[:300], y)
    y = campo("Localização:", geo, y)
    y = campo("SHA-256 do termo original:", hash_pdf_original, y)
    if oferecidos:
        recusados = [e for e in oferecidos if e not in aceitos]
        y = campo("Finalidades aceitas:", ", ".join(aceitos) or "nenhuma", y)
        y = campo("Não aceitas:", ", ".join(recusados) or "nenhuma", y)

    y -= 4 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margem, y, "Assinatura do titular:")
    y -= 3 * mm
    caixa_h = 40 * mm
    c.rect(margem, y - caixa_h, largura_texto, caixa_h)
    img = ImageReader(BytesIO(assinatura_png))
    iw, ih = img.getSize()
    escala = min((largura_texto - 6 * mm) / iw, (caixa_h - 6 * mm) / ih)
    w, h = iw * escala, ih * escala
    c.drawImage(img, margem + (largura_texto - w) / 2, y - caixa_h + (caixa_h - h) / 2,
                width=w, height=h, mask="auto")
    y -= caixa_h + 8 * mm

    declaracao = ("Documento assinado eletronicamente pelo titular em atendimento presencial, "
                  "mediante leitura do termo, confirmação de identidade e registro das suas escolhas "
                  "(as descrições das finalidades estão na seção 4 do termo). A integridade do termo "
                  "original pode ser verificada pelo hash SHA-256 acima.")
    c.setFont("Helvetica-Oblique", 8)
    for ln in simpleSplit(declaracao, "Helvetica-Oblique", 8, largura_texto):
        c.drawString(margem, y, ln)
        y -= 4 * mm
    c.showPage()
    c.save()
    buf.seek(0)

    # ---- 2) junta termo original (refeito do texto) + comprovante
    original = gerar_pdf_bytes(texto_termo)
    writer = PdfWriter()
    for pagina in PdfReader(BytesIO(original)).pages:
        writer.add_page(pagina)
    for pagina in PdfReader(buf).pages:
        writer.add_page(pagina)
    saida = BytesIO()
    writer.write(saida)
    return saida.getvalue()