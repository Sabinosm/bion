"""Rotas JSON do dominio Catalogo (exames e medicamentos de referencia)."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_medico_ou_enfermeiro
from .service import CatalogoExamesService, CatalogoMedicamentosService

bp_exames = Blueprint("catalogo_exames", __name__)
bp_medicamentos = Blueprint("catalogo_medicamentos", __name__)

_svc_exames = CatalogoExamesService()
_svc_medicamentos = CatalogoMedicamentosService()


# ---------------- Exames ----------------

@bp_exames.get("/")
@requer_login
def lista_exames():
    termo = request.args.get("q")
    itens = _svc_exames.buscar(termo) if termo else _svc_exames.listar()
    return json_success(data=[e.to_dict() for e in itens])


@bp_exames.get("/<uuid>")
@requer_login
def detalhe_exame(uuid):
    try:
        e = _svc_exames.buscar_por_uuid(uuid)
        return json_success(data=e.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_exames.post("/")
@requer_medico_ou_enfermeiro
def criar_exame():
    dados = request.get_json(silent=True) or {}
    try:
        e = _svc_exames.criar(dados)
        return json_success(data=e.to_dict(), message="Exame cadastrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# ---------------- Medicamentos ----------------

@bp_medicamentos.get("/")
@requer_login
def lista_medicamentos():
    termo = request.args.get("q")
    itens = _svc_medicamentos.buscar(termo) if termo else _svc_medicamentos.listar()
    return json_success(data=[m.to_dict() for m in itens])


@bp_medicamentos.get("/<uuid>")
@requer_login
def detalhe_medicamento(uuid):
    try:
        m = _svc_medicamentos.buscar_por_uuid(uuid)
        return json_success(data=m.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_medicamentos.get("/<uuid>/interacoes")
@requer_medico_ou_enfermeiro
def interacoes_medicamento(uuid):
    try:
        interacoes = _svc_medicamentos.verificar_interacoes(uuid)
        return json_success(data=[i.to_dict() for i in interacoes])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_medicamentos.post("/")
@requer_medico_ou_enfermeiro
def criar_medicamento():
    dados = request.get_json(silent=True) or {}
    try:
        m = _svc_medicamentos.criar(dados)
        return json_success(data=m.to_dict(), message="Medicamento cadastrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
