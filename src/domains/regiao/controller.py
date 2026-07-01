"""Rotas JSON do dominio Regiao Geografica."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, requer_login
from .service import RegiaoService

bp = Blueprint("regiao", __name__)
_svc = RegiaoService()


@bp.get("/")
@requer_login
def lista():
    tipo = request.args.get("tipo")
    itens = _svc.listar(tipo)
    return json_success(data=[r.to_dict() for r in itens])


@bp.get("/<uuid>")
@requer_login
def detalhe(uuid):
    try:
        r = _svc.buscar_por_uuid(uuid)
        return json_success(data=r.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/")
@requer_admin
def criar():
    dados = request.get_json(silent=True) or {}
    try:
        r = _svc.criar(dados)
        return json_success(data=r.to_dict(), message="Região criada com sucesso.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
