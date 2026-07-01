"""Rotas JSON do dominio Auditoria (somente leitura para administradores)."""

from flask import Blueprint, request

from src.core.responses import json_success
from src.core.session import requer_admin
from .service import AuditoriaService

bp = Blueprint("auditoria", __name__)
_svc = AuditoriaService()


@bp.get("/acessos")
@requer_admin
def listar_acessos():
    id_usuario = request.args.get("id_usuario", type=int)
    itens = _svc.listar_acessos(id_usuario)
    return json_success(data=[i.to_dict() for i in itens])


@bp.get("/alteracoes")
@requer_admin
def listar_alteracoes():
    tabela = request.args.get("tabela")
    uuid_registro = request.args.get("uuid_registro")
    itens = _svc.listar_alteracoes(tabela, uuid_registro)
    return json_success(data=[i.to_dict() for i in itens])
