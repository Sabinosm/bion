"""
Rotas de assinatura digital LGPD via QR code.
Registrado sob /v1/api/pacientes/lgpd (mesmo prefixo do LgpdController).

PÚBLICAS (paciente no celular, o token é a autenticação):
  GET  /assinar/<token>                     dados para montar a tela
  GET  /assinar/<token>/termo.pdf           paciente baixa o termo (PDF refeito em memória)
  POST /assinar/<token>                     registra a assinatura
  GET  /assinar/<token>/comprovante.pdf     paciente baixa a PRÓPRIA cópia assinada (janela curta)

PROTEGIDAS (médico/enfermeiro):
  POST /<uuid_paciente>/gerar-link-assinatura
  GET  /assinatura/<token>/status           saber se o paciente já assinou
  POST /assinatura/<token>/cancelar         invalida um link pendente
  GET  /comprovante/<uuid_consentimento>    metadados do comprovante
  GET  /download-pdf/<uuid_consentimento>   PDF assinado (refeito em memória do banco)

Dados do usuário logado: get_id_usuario_sessao(), get_id_empresa_sessao().
O front é responsável por renderizar o PDF, detectar scroll, capturar o canvas
e enviar tudo como JSON.

Auditoria: nas protegidas, só o comprovante e o PDF assinado usam acesso_auditado (gerar e
cancelar link ficam na própria sessão de assinatura). As públicas NÃO têm
usuário logado; a trilha delas é a própria sessão (IP, user-agent, horário)
e o consentimento criado.
"""

from io import BytesIO

from flask import Blueprint, request, send_file

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico,
    get_id_usuario_sessao,
    get_id_empresa_sessao,
)
from src.domains.paciente.services import ConsentimentoDigitalService
from src.domains.auditoria.acaoSensivel import acesso_auditado, ip_cliente as _ip_cliente

bp = Blueprint("paciente_lgpd_digital", __name__)
_svc = ConsentimentoDigitalService()


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


@bp.get("/assinar/<token>/termo.pdf")
def baixar_termo(token: str):
    """PDF do termo para o paciente baixar/ler. Só enquanto o link está pendente.
    X-SHA256 = hash do PDF, o mesmo hash_pdf_original mostrado na tela."""
    try:
        pdf, sha = _svc.obter_termo_pdf(token)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    resp = send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="termo_consentimento_lgpd.pdf")
    resp.headers["X-SHA256"] = sha
    return resp


@bp.get("/assinar/<token>/comprovante.pdf")
def baixar_copia(token: str):
    """Cópia assinada para o paciente, logo após assinar. Janela curta (ver
    CONSENT_JANELA_COPIA_MIN); depois disso, só a clínica emite (rota do médico)."""
    try:
        pdf = _svc.obter_copia_assinada(token)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    resp = send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="comprovante_consentimento_lgpd.pdf")
    resp.headers["Cache-Control"] = "no-store"          # contém nome, CPF e assinatura
    return resp


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
def gerar_link(uuid_paciente: str):
    """
    Body JSON:  { "versao_termo": "lgpd-v1.0-2026" }
    Texto e PDF são gerados no servidor: template da versão + dados da empresa da sessão.
    """
    dados = request.get_json(silent=True) or {}
    try:
        resultado = _svc.gerar_link_assinatura(
            uuid_paciente=uuid_paciente,
            id_medico=get_id_usuario_sessao(),
            id_empresa=get_id_empresa_sessao(),
            versao_termo=dados.get("versao_termo"),
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
        return json_error(ex.message, ex.status_code), {"operacao": "NOOP"}


@bp.get("/download-pdf/<uuid_consentimento>")
@requer_papel_clinico("medico", "enfermeiro")
@acesso_auditado(recurso="pdf assinado de consentimento", operacao="exportacao")
def download_pdf(uuid_consentimento: str):
    """PDF assinado. Recebe o UUID do consentimento (nunca um caminho): o service
    confere a empresa e REFAZ o PDF em memória a partir do banco (nada fica em disco).
    X-Integridade: 'confere' se o SHA-256 refeito bate com o hash registrado na
    assinatura; 'divergente' se não (ex.: biblioteca de PDF atualizada, paciente anonimizado)."""
    try:
        pdf, confere = _svc.obter_pdf_assinado(uuid_consentimento, get_id_empresa_sessao())
    except BionException as ex:
        return json_error(ex.message, ex.status_code), {"operacao": "NOOP"}
    resp = send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"termo_assinado_{uuid_consentimento}.pdf",
    )
    resp.headers["Cache-Control"] = "no-store"          # contém nome, CPF e assinatura
    resp.headers["X-Integridade"] = "confere" if confere else "divergente"
    return resp