"""Rotas JSON do dominio Usuario (CRUD administrativo)."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, requer_login
from .service import UsuarioService

bp = Blueprint("usuario", __name__)
_svc = UsuarioService()


@bp.get("/")
@requer_admin
def lista():
    usuarios = _svc.listar()
    return json_success(data=[u.to_dict() for u in usuarios])


@bp.get("/<uuid>")
@requer_login
def detalhe(uuid):
    try:
        u = _svc.buscar_por_uuid(uuid)
        return json_success(data=u.to_dict())
    except BionException as e:
        return json_error(e.message, e.status_code)


@bp.post("/")
@requer_admin
def criar():
    dados = request.get_json(silent=True) or {}
    try:
        u = _svc.criar(dados)
        return json_success(data=u.to_dict(), message="Usuário criado com sucesso.", status=201)
    except BionException as e:
        return json_error(e.message, e.status_code)


@bp.put("/<uuid>")
@requer_admin
def atualizar(uuid):
    dados = request.get_json(silent=True) or {}
    try:
        u = _svc.atualizar(uuid, dados)
        return json_success(data=u.to_dict(), message="Usuário atualizado.")
    except BionException as e:
        return json_error(e.message, e.status_code)


@bp.post("/<uuid>/desativar")
@requer_admin
def desativar(uuid):
    try:
        u = _svc.desativar(uuid)
        return json_success(data=u.to_dict(), message="Usuário desativado.")
    except BionException as e:
        return json_error(e.message, e.status_code)


@bp.post("/<uuid>/ativar")
@requer_admin
def ativar(uuid):
    try:
        u = _svc.ativar(uuid)
        return json_success(data=u.to_dict(), message="Usuário ativado.")
    except BionException as e:
        return json_error(e.message, e.status_code)
