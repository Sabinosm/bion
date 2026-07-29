"""
Rotas JSON de dados clinicos do paciente: alergias, doencas cronicas e
medicamentos em uso.

ADICIONADO: rota de nova reação numa alergia já existente (capacidade
nova, antes o schema só suportava uma reação por alergia).
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
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
@requer_papel("medico", "enfermeiro")
def adicionar_alergia(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        a = _svc.adicionar_alergia(uuid_paciente, dados)
        return json_success(data=a.to_dict(), message="Alergia registrada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# NOVO: registra uma reação adicional numa alergia já existente
@bp.post("/alergias/<uuid_alergia>/reacoes")
@requer_papel("medico", "enfermeiro")
def adicionar_reacao(uuid_alergia):
    dados = request.get_json(silent=True) or {}
    try:
        a = _svc.adicionar_reacao(uuid_alergia, dados)
        return json_success(data=a.to_dict(), message="Reação registrada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# NOVO: remove a alergia inteira (com todo o histórico de reações)
@bp.delete("/alergias/<uuid_alergia>")
@requer_papel("admin", "medico")
def remover_alergia(uuid_alergia):
    try:
        _svc.remover_alergia(uuid_alergia)
        return json_success(message="Alergia removida.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# NOVO: remove apenas uma reação específica, mantendo a alergia e o
# restante do histórico intactos
@bp.delete("/alergias/reacoes/<uuid_reacao>")
@requer_papel("admin", "medico")
def remover_reacao(uuid_reacao):
    try:
        _svc.remover_reacao(uuid_reacao)
        return json_success(message="Reação removida.")
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
@requer_papel("medico", "enfermeiro")
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
@requer_papel("medico", "enfermeiro")
def adicionar_medicamento_em_uso(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        m = _svc.adicionar_medicamento_em_uso(uuid_paciente, dados)
        return json_success(data=m.to_dict(), message="Medicamento em uso registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)