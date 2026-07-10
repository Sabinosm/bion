"""Rotas JSON da entidade ProtocoloCatalogo."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import ProtocoloCatalogoService

bp_protocolo = Blueprint("protocolo", __name__)
_svc = ProtocoloCatalogoService()


@bp_protocolo.get("/")
@requer_login
def lista_protocolos():
    """Lista todos os ProtocoloCatalogo cadastrados."""
    itens = _svc.listar()
    return json_success(data=[p.to_dict() for p in itens])


@bp_protocolo.get("/<uuid>")
@requer_login
def detalhe_protocolo(uuid):
    """Retorna os detalhes de um ProtocoloCatalogo pelo UUID."""
    try:
        p = _svc.buscar_por_uuid(uuid)
        return json_success(data=p.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_protocolo.post("/")
@requer_papel("admin")
def criar_protocolo():
    """Cadastra um novo ProtocoloCatalogo."""
    dados = request.get_json(silent=True) or {}
    try:
        p = _svc.criar(dados)
        return json_success(data=p.to_dict(), message="Protocolo cadastrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
