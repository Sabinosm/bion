"""
Rotas JSON da entidade CatalogoModulos.

NOTA: este controller não existia no código original — o service já
estava implementado mas sem nenhuma rota associada. Rotas de leitura
básicas foram criadas aqui para expor o catálogo já pronto.
"""

from flask import Blueprint

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login
from .service import CatalogoModulosService

bp_catalogo_modulos = Blueprint("catalogo_modulos", __name__)
_svc = CatalogoModulosService()


@bp_catalogo_modulos.get("/")
@requer_login
def lista_modulos():
    """Lista todos os CatalogoModulos cadastrados."""
    itens = _svc.listar()
    return json_success(data=[m.to_dict() for m in itens])


@bp_catalogo_modulos.get("/<uuid>")
@requer_login
def detalhe_modulo(uuid):
    """Retorna os detalhes de um CatalogoModulos pelo UUID."""
    try:
        m = _svc.buscar_por_uuid(uuid)
        return json_success(data=m.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
