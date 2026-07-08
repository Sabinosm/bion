"""Rotas JSON do dominio Usuario (CRUD administrativo)."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, id_empresa_sessao
from .service import UsuarioService
from flask import Blueprint, request, g

bp = Blueprint("usuario", __name__)
_svc = UsuarioService()


@bp.get("/")
@requer_papel("admin")
def lista():
    usuarios = _svc.listar(id_empresa_sessao())
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
@requer_papel("admin")
def criar():
    
    dados = request.get_json(silent=True) or {}
    try:
        u = _svc.criar(id_empresa=id_empresa_sessao(),dados=dados, commitar=True)
        return json_success(data=u.to_dict(), message="Usuário criado com sucesso.", status=201)
    except BionException as e:
        return json_error(e.message, e.status_code)


@bp.put("/<uuid>")
@requer_login
def atualizar(uuid):
    if uuid != g.uuid_usuario and g.tipo_usuario != "admin":
        return json_error("Você só pode atualizar o seu próprio cadastro.", 403)

    dados = request.get_json(silent=True) or {}
    try:
        u = _svc.atualizar(uuid, dados, solicitante_eh_admin=(g.tipo_usuario == "admin"))
        return json_success(data=u.to_dict(), message="Usuário atualizado.")
    except BionException as e:
        return json_error(e.message, e.status_code)


@bp.post("/<uuid>/desativar")
@requer_papel("admin")
def desativar(uuid):
    try:
        u = _svc.desativar(uuid)
        return json_success(data=u.to_dict(), message="Usuário desativado.")
    except BionException as e:
        return json_error(e.message, e.status_code)


@bp.post("/<uuid>/ativar")
@requer_papel("admin")
def ativar(uuid):
    try:
        u = _svc.ativar(uuid)
        return json_success(data=u.to_dict(), message="Usuário ativado.")
    except BionException as e:
        return json_error(e.message, e.status_code)


# TODO parte do admin ( primeiro to fazendo o 2FA depois eu sigo para essa parte)

@bp.route("/<uuid>/usuarios/<uuid_usuario>/resetar-2fa", methods=["POST"])
@requer_papel("admin")
def resetar_2fa(uuid_usuario):
    _svc.reset_2fa(uuid_usuario)
 
 
@bp.route("/<uuid>/usuarios/<uuid_usuario>/resetar-completo", methods=["POST"])
@requer_papel("admin")
def resetar_completo(uuid_usuario):
    _svc.reset_total(uuid_usuario)