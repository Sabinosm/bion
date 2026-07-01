"""
Rotas JSON de dados clinicos do paciente: alergias, doencas cronicas e
medicamentos em uso (equivalente ao antigo dominio `dados_clinicos`).
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_medico_ou_enfermeiro
from src.domains.paciente.services import DadosClinicosService

bp = Blueprint("paciente_clinico", __name__)
_svc = DadosClinicosService()


# ---------------- Alergias ----------------

@bp.get("/<uuid_paciente>/alergias")
@requer_login
def listar_alergias(uuid_paciente):
    try:
        itens = _svc.listar_alergias(uuid_paciente)
        return json_success(data=[a.to_dict() for a in itens])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/<uuid_paciente>/alergias")
@requer_medico_ou_enfermeiro
def adicionar_alergia(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        a = _svc.adicionar_alergia(uuid_paciente, dados)
        return json_success(data=a.to_dict(), message="Alergia registrada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# ---------------- Doenças crônicas ----------------

@bp.get("/<uuid_paciente>/doencas-cronicas")
@requer_login
def listar_doencas(uuid_paciente):
    try:
        itens = _svc.listar_doencas(uuid_paciente)
        return json_success(data=[d.to_dict() for d in itens])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/<uuid_paciente>/doencas-cronicas")
@requer_medico_ou_enfermeiro
def adicionar_doenca(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        d = _svc.adicionar_doenca(uuid_paciente, dados)
        return json_success(data=d.to_dict(), message="Doença crônica registrada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# ---------------- Medicamentos em uso ----------------

@bp.get("/<uuid_paciente>/medicamentos-em-uso")
@requer_login
def listar_medicamentos_em_uso(uuid_paciente):
    try:
        itens = _svc.listar_medicamentos_em_uso(uuid_paciente)
        return json_success(data=[m.to_dict() for m in itens])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/<uuid_paciente>/medicamentos-em-uso")
@requer_medico_ou_enfermeiro
def adicionar_medicamento_em_uso(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        m = _svc.adicionar_medicamento_em_uso(uuid_paciente, dados)
        return json_success(data=m.to_dict(), message="Medicamento em uso registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
