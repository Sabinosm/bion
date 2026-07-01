"""
Rotas JSON de consentimento LGPD e anonimizacao de paciente.
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_medico_ou_enfermeiro, requer_admin
from src.domains.paciente.services import ConsentimentoService, PacienteService

bp = Blueprint("paciente_lgpd", __name__)
_svc = ConsentimentoService()
_svc_paciente = PacienteService()


@bp.get("/<uuid_paciente>/consentimentos")
@requer_login
def listar(uuid_paciente):
    try:
        itens = _svc.listar_por_paciente(uuid_paciente)
        return json_success(data=[c.to_dict() for c in itens])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/<uuid_paciente>/consentimentos")
@requer_medico_ou_enfermeiro
def registrar(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc.registrar(uuid_paciente, dados, session["usuario_id"])
        return json_success(data=c.to_dict(), message="Consentimento registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/<uuid_paciente>/consentimentos/revogar")
@requer_medico_ou_enfermeiro
def revogar(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc.revogar(uuid_paciente, dados.get("motivo"))
        return json_success(data=c.to_dict(), message="Consentimento revogado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/<uuid_paciente>/anonimizar")
@requer_admin
def anonimizar(uuid_paciente):
    """Exclusão de dados pessoais mediante solicitação do titular (LGPD)."""
    try:
        p = _svc_paciente.anonimizar(uuid_paciente)
        return json_success(data=p.to_dict(), message="Dados pessoais removidos com sucesso.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
