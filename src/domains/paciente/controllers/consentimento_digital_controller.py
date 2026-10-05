"""
Rotas de assinatura digital LGPD via QR code.
Registrado sob /v1/api/pacientes/lgpd (mesmo prefixo do LgpdController).

PÚBLICAS (paciente no celular, o token é a autenticação):
  GET  /assinar/<token>                     dados para montar a tela
  POST /assinar/<token>                     registra a assinatura

PROTEGIDAS (médico/enfermeiro):
  POST /<uuid_paciente>/gerar-link-assinatura
  GET  /assinatura/<token>/status           saber se o paciente já assinou
  POST /assinatura/<token>/cancelar         invalida um link pendente
  GET  /comprovante/<uuid_consentimento>    metadados do comprovante
  GET  /download-pdf/<uuid_consentimento>   PDF assinado

Dados do usuário logado: get_id_usuario_sessao(), get_id_empresa_sessao().
O front é responsável por renderizar o PDF, detectar scroll, capturar o canvas
e enviar tudo como JSON.

Auditoria: as rotas protegidas usam acesso_auditado. As públicas NÃO têm
usuário logado; a trilha delas é a própria sessão (IP, user-agent, horário)
e o consentimento criado.
"""

import os

from flask import Blueprint, request, send_file

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico,
    get_id_usuario_sessao,
    get_id_empresa_sessao,
)
from src.domains.paciente.services import ConsentimentoDigitalService
from src.domains.auditoria.acaoSensivel import acesso_auditado

bp = Blueprint("paciente_lgpd_digital", __name__)
_svc = ConsentimentoDigitalService()


def _ip_cliente() -> str:
    """IP do cliente sem confiar cegamente no X-Forwarded-For.

    TRUSTED_PROXY_HOPS = quantos proxies SEUS ficam na frente do Flask
    (0 = nenhum: usa o remote_addr; 1 = nginx/ALB: pega o último IP da
    cadeia, que foi o proxy que anexou). O cliente pode forjar o começo
    da cadeia, mas não o trecho que o seu proxy anexa."""
    hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
    xff = request.headers.get("X-Forwarded-For", "")
    if hops > 0 and xff:
        partes = [p.strip() for p in xff.split(",") if p.strip()]
        if len(partes) >= hops:
            return partes[-hops]
    return request.remote_addr


# ============================================================================
# ROTAS PÚBLICAS
# ============================================================================
# TODO: aplicar rate limit nestas duas rotas (ex.: Flask-Limiter, por IP e token).

@bp.get("/assinar/<token>")
def obter_dados_assinatura(token: str):
    """JSON com dados do paciente, texto do termo, hash do PDF e escopos disponíveis."""
    try:
        return json_success(data=_svc.obter_dados_sessao(token))
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/assinar/<token>")
def registrar_assinatura(token: str):
    """
    Body JSON:
    {
      "confirmo_identidade": true,
      "declaro_consentimento": true,
      "assinatura_canvas": "data:image/png;base64,...",
      "hash_pdf_original": "<sha256 recebido no GET>",
      "user_agent": "(opcional; o do servidor tem prioridade)",
      "geolocalizacao": "São Paulo, SP",
      "geo_divergente": false,
      "escopos_selecionados": ["marketing", "pesquisa"]
    }
    """
    dados = request.get_json(silent=True) or {}
    try:
        resultado = _svc.registrar_assinatura(
            token,
            dados,
            ip_paciente=_ip_cliente(),
            user_agent_servidor=request.headers.get("User-Agent"),
        )
        return json_success(data=resultado, message="Consentimento assinado com sucesso.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# ============================================================================
# ROTAS PROTEGIDAS
# ============================================================================

@bp.post("/<uuid_paciente>/gerar-link-assinatura")
@requer_papel_clinico("medico", "enfermeiro")
@acesso_auditado(recurso="gerar link de assinatura de consentimento", operacao="escrita")
def gerar_link(uuid_paciente: str):
    """
    Body JSON:
    {
      "id_unidade": 42,
      "versao_termo": "lgpd-v2.1-2026",
      "pdf_termo_path": "/app/storage/termos/lgpd-v2.1.pdf",   (dentro de CONSENT_PDF_TERMOS)
      "texto_termo": "Texto integral do termo..."
    }
    """
    dados = request.get_json(silent=True) or {}
    try:
        resultado = _svc.gerar_link_assinatura(
            uuid_paciente=uuid_paciente,
            id_medico=get_id_usuario_sessao(),
            id_unidade=dados.get("id_unidade"),
            id_empresa=get_id_empresa_sessao(),
            versao_termo=dados.get("versao_termo"),
            pdf_termo_path=dados.get("pdf_termo_path"),
            texto_termo=dados.get("texto_termo"),
            ip_medico=_ip_cliente(),
        )
        return json_success(data=resultado, status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/assinatura/<token>/status")
@requer_papel_clinico("medico", "enfermeiro")
def status_assinatura(token: str):
    """Polling do front do médico: pendente | usado | expirado.
    Sem auditoria: é consulta repetida de estado, sem dado clínico."""
    try:
        return json_success(data=_svc.obter_status_sessao(token, get_id_empresa_sessao()))
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/assinatura/<token>/cancelar")
@requer_papel_clinico("medico", "enfermeiro")
@acesso_auditado(recurso="cancelar link de assinatura de consentimento", operacao="escrita")
def cancelar_link(token: str):
    try:
        return json_success(data=_svc.cancelar_link(token, get_id_empresa_sessao()), message="Link cancelado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/comprovante/<uuid_consentimento>")
@requer_papel_clinico("medico", "enfermeiro")
@acesso_auditado(recurso="comprovante de consentimento", operacao="leitura")
def obter_comprovante(uuid_consentimento: str):
    try:
        return json_success(data=_svc.obter_comprovante(uuid_consentimento, get_id_empresa_sessao()))
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/download-pdf/<uuid_consentimento>")
@requer_papel_clinico("medico", "enfermeiro")
@acesso_auditado(recurso="pdf assinado de consentimento", operacao="leitura")
def download_pdf(uuid_consentimento: str):
    """PDF assinado. Recebe o UUID do consentimento (nunca um caminho): o service
    confere a empresa e resolve o arquivo dentro do storage."""
    try:
        caminho = _svc.obter_arquivo_pdf(uuid_consentimento, get_id_empresa_sessao())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    return send_file(
        caminho,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"termo_assinado_{uuid_consentimento}.pdf",
    )