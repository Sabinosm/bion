"""Rotas JSON do dominio Configuracao (preferencias por usuario)."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login
from .service import ConfiguracaoService

bp = Blueprint("configuracao", __name__)
_svc = ConfiguracaoService()


@bp.get("/")
@requer_login
def minha_configuracao():
    cfg = _svc.obter_ou_criar(session["usuario_id"])
    return json_success(data=cfg.to_dict())


@bp.put("/")
@requer_login
def atualizar():
    dados = request.get_json(silent=True) or {}
    try:
        cfg = _svc.atualizar(session["usuario_id"], dados.get("configuracoes", {}))
        return json_success(data=cfg.to_dict(), message="Configurações atualizadas.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/protocolos")
@requer_login
def listar_protocolos():
    protocolos = _svc.listar_protocolos(session["usuario_id"])
    return json_success(data=[p.to_dict() for p in protocolos])


@bp.put("/protocolos/<int:id_protocolo>/habilitar")
@requer_login
def habilitar_protocolo(id_protocolo):
    dados = request.get_json(silent=True) or {}
    try:
        protocolo = _svc.habilitar_protocolo(
            session["usuario_id"], id_protocolo, dados.get("configuracoes")
        )
        return json_success(data=protocolo.to_dict(), message="Protocolo habilitado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.put("/protocolos/<int:id_protocolo>/desabilitar")
@requer_login
def desabilitar_protocolo(id_protocolo):
    try:
        protocolo = _svc.desabilitar_protocolo(session["usuario_id"], id_protocolo)
        return json_success(data=protocolo.to_dict(), message="Protocolo desabilitado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)