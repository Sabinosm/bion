
from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import CatalogoExamesService

bp_exames = Blueprint("catalogo_exames", __name__)
_svc = CatalogoExamesService()


@bp_exames.get("/")
@requer_login
def lista_exames():
    termo = request.args.get("q")
    itens = _svc.buscar(termo) if termo else _svc.listar()
    return json_success(data=[e.to_dict() for e in itens])


@bp_exames.get("/<uuid>")
@requer_login
def detalhe_exame(uuid):
    try:
        e = _svc.buscar_por_uuid(uuid)
        return json_success(data=e.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_exames.post("/")
@requer_papel("medico")
def criar_exame():
    dados = request.get_json(silent=True) or {}
    try:
        e = _svc.criar(dados)
        return json_success(data=e.to_dict(), message="Exame cadastrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)

