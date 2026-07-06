"""
Rotas JSON de dados cadastrais do paciente (Paciente + Paciente_pessoal).

PII (nome, cpf, telefone, email, endereco) so e devolvida em texto claro
para medico/enfermeiro; qualquer outro perfil autenticado ve apenas os
dados clinicos nao-identificaveis do Paciente.
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_medico_ou_enfermeiro
from src.domains.paciente.services import PacienteService

bp = Blueprint("paciente_pessoal", __name__)
_svc = PacienteService()


def _serializar(paciente, com_pii: bool):
    d = paciente.to_dict()
    if com_pii:
        d["pessoal"] = _svc.dados_pessoais_descriptografados(paciente)
    return d


@bp.get("/")
@requer_login
def lista():
    com_pii = session.get("tipo_usuario") in ("medico", "enfermeiro")
    pacientes = _svc.listar()
    return json_success(data=[_serializar(p, com_pii) for p in pacientes])


@bp.get("/<uuid>")
@requer_login
def detalhe(uuid):
    com_pii = session.get("tipo_usuario") in ("medico", "enfermeiro")
    try:
        p = _svc.buscar_por_uuid(uuid)
        return json_success(data=_serializar(p, com_pii))
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/")
@requer_medico_ou_enfermeiro
def cadastrar():
    dados = request.get_json(silent=True) or {}
    try:
        p = _svc.cadastrar(dados, session["id_usuario"])
        return json_success(data=_serializar(p, True), message="Paciente cadastrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.put("/<uuid>")
@requer_medico_ou_enfermeiro
def atualizar(uuid):
    dados = request.get_json(silent=True) or {}
    try:
        p = _svc.atualizar(uuid, dados)
        return json_success(data=_serializar(p, True), message="Paciente atualizado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
