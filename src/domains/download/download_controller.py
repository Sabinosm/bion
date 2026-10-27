"""download_controller.py -- rotas de download em PDF (atendimento, consulta, prescrição).

Arquivo PROVISÓRIO: reúne as 3 rotas num blueprint próprio só para não mexer nos outros
controllers por enquanto. Quando for reposicionar, cada rota vira um método do controller do seu
domínio, com o caminho curto indicado no comentário "DESTINO" de cada uma.

Registro (única linha fora deste arquivo, para testar):
    from src.domains.download_controller import bp_download_pdf
    app.register_blueprint(bp_download_pdf, url_prefix="/v1/api")

Acesso: só enfermeiro e médico, da própria empresa (o service filtra por id_empresa da sessão;
404 igual para "não existe" e "é de outra empresa"). Sem @acesso_auditado, por decisão: o PDF só
reapresenta dados que já existem. Não fica nada em disco; a resposta vai com no-store.

Front: baixar com fetch (mesma origem, cookie de sessão) e converter a resposta em blob; um
<a href> direto também funciona por ser GET com cookie.
"""
from io import BytesIO

from flask import Blueprint, request, send_file

from src.core.exceptions import BionException
from src.core.responses import json_error
from src.core.session import get_id_empresa_sessao, get_id_usuario_sessao, requer_papel_clinico
from .download_atendimento_service import DownloadAtendimentoService
from .download_consulta_service import DownloadConsultaService
from .download_prescricao_service import DownloadPrescricaoService

bp_download_pdf = Blueprint("download_pdf", __name__)

_atendimento = DownloadAtendimentoService()
_consulta = DownloadConsultaService()
_prescricao = DownloadPrescricaoService()


def _resposta_pdf(pdf: bytes, nome: str):
    resp = send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=nome)
    resp.headers["Cache-Control"] = "no-store, max-age=0"       # dado clínico: nada de cache no navegador/proxy
    resp.headers["Pragma"] = "no-cache"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


class DownloadPdfController:

    @staticmethod
    @bp_download_pdf.get("/atendimentos/<uuid>/pdf")           # DESTINO: bp_atendimento  GET "/<uuid>/pdf"
    @requer_papel_clinico("enfermeiro", "medico")
    def pdf_atendimento(uuid):
        """?modo=resumo|detalhado (padrão: resumo). Resumo só de atendimento finalizado (409 nos demais)."""
        try:
            pdf, nome = _atendimento.gerar(uuid, get_id_empresa_sessao(), get_id_usuario_sessao(),
                                           request.args.get("modo", "resumo"))
            return _resposta_pdf(pdf, nome)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_download_pdf.get("/consultas/<uuid>/pdf")              # DESTINO: bp_consulta  GET "/<uuid>/pdf"
    @requer_papel_clinico("enfermeiro", "medico")
    def pdf_consulta(uuid):
        """?modo=resumo|detalhado (padrão: resumo). Consulta aberta sai com marca PARCIAL."""
        try:
            pdf, nome = _consulta.gerar(uuid, get_id_empresa_sessao(), get_id_usuario_sessao(),
                                        request.args.get("modo", "resumo"))
            return _resposta_pdf(pdf, nome)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_download_pdf.get("/prescricoes/<uuid_resultado>/pdf")  # DESTINO: controller de prescrição  GET "/<uuid_resultado>/pdf"
    @requer_papel_clinico("enfermeiro", "medico")
    def pdf_prescricao(uuid_resultado):
        """Prescrição CONFIRMADA (receita + pedido de exames). Rascunho => 409."""
        try:
            pdf, nome = _prescricao.gerar(uuid_resultado, get_id_empresa_sessao(), get_id_usuario_sessao())
            return _resposta_pdf(pdf, nome)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
