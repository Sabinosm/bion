"""Rotas JSON da entidade ProtocoloCatalogo."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_admin
from src.core.session.sessaoUsuarios import get_id_empresa_sessao 
from .shared.services.protocolo_catalogo_service import ProtocoloCatalogoService

bp_protocolo = Blueprint("protocolo", __name__)
_svc = ProtocoloCatalogoService()


class ProtocoloController():
    
    @staticmethod
    @bp_protocolo.get("/")
    @requer_login
    def lista_protocolos():
        """Lista todos os ProtocoloCatalogo cadastrados."""
        itens = _svc.listar()
        return json_success(data=[p.to_dict() for p in itens])


    @staticmethod
    @bp_protocolo.get("/<uuid>")
    @requer_login
    def detalhe_protocolo(uuid):
        """Retorna os detalhes de um ProtocoloCatalogo pelo UUID."""
        try:
            p = _svc.buscar_por_uuid(uuid)
            return json_success(data=p.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
    
    # shared/controllers/protocolo_catalogo_controller.py — rotas novas

    @staticmethod
    @bp_protocolo.get("/catalogo")
    @requer_login
    def listar_catalogo():
        """Página de catálogo, sem filtro."""
        id_empresa = get_id_empresa_sessao()
        itens = _svc.listar_catalogo(id_empresa)
        return json_success(data=itens)


    @staticmethod
    @bp_protocolo.get("/catalogo/filtrar")
    @requer_login
    def listar_catalogo_filtrado():
        """Página de catálogo, com filtros via query string:
        ?tipo_protocolo=escore-ponderado&escopo_populacao=adulto&escopo_uso=triagem&apenas_liberados=true"""
        id_empresa = get_id_empresa_sessao()
        tipo_protocolo = request.args.get("tipo_protocolo")
        escopo_populacao = request.args.get("escopo_populacao")
        escopo_uso = request.args.get("escopo_uso")
        apenas_liberados = request.args.get("apenas_liberados", default="false") == "true"
        pagina = request.args.get("pagina", default=0, type=int)

        itens = _svc.listar_catalogo_filtrado(
            id_empresa, tipo_protocolo, escopo_populacao, escopo_uso, apenas_liberados, offset=pagina * 20
        )
        return json_success(data=itens)
