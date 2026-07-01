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
