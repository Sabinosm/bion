from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import CatalogoMedicamentosService

bp_medicamentos = Blueprint("catalogo_medicamentos", __name__)
_svc = CatalogoMedicamentosService()

@bp_medicamentos.get("/")
@requer_login
def lista_medicamentos():
    termo = request.args.get("q")
    itens = _svc.buscar(termo) if termo else _svc.listar()
    return json_success(data=[m.to_dict() for m in itens])


@bp_medicamentos.get("/<uuid>")
@requer_login
def detalhe_medicamento(uuid):
    try:
        m = _svc.buscar_por_uuid(uuid)
        return json_success(data=m.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_medicamentos.get("/<uuid>/interacoes")
@requer_papel("medico")
def interacoes_medicamento(uuid):
    try:
        interacoes = _svc.verificar_interacoes(uuid)
        return json_success(data=[i.to_dict() for i in interacoes])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_medicamentos.post("/")
@requer_papel("medico")
def criar_medicamento():
    dados = request.get_json(silent=True) or {}
    try:
        m = _svc.criar(dados)
        return json_success(data=m.to_dict(), message="Medicamento cadastrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
