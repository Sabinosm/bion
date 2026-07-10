"""
Rotas JSON da entidade CatalogoFluxogramasMts.

NOTA: este controller não existia no código original — o service já
estava implementado mas sem nenhuma rota associada. Rotas de leitura
básicas foram criadas aqui para expor o catálogo já pronto.
"""

from flask import Blueprint

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login
from .service import CatalogoFluxogramasMtsService

bp_catalogo_fluxogramas_mts = Blueprint("catalogo_fluxogramas_mts", __name__)
_svc = CatalogoFluxogramasMtsService()


@bp_catalogo_fluxogramas_mts.get("/")
@requer_login
def lista_fluxogramas_mts():
    """Lista todos os CatalogoFluxogramasMts cadastrados."""
    itens = _svc.listar()
    return json_success(data=[f.to_dict() for f in itens])


@bp_catalogo_fluxogramas_mts.get("/<uuid>")
@requer_login
def detalhe_fluxograma_mts(uuid):
    """Retorna os detalhes de um CatalogoFluxogramasMts pelo UUID."""
    try:
        f = _svc.buscar_por_uuid(uuid)
        return json_success(data=f.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
