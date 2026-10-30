"""protocolo_catalogo_controller.py

Rotas JSON do catálogo de protocolos: listagem geral, páginas de catálogo
(com ou sem filtros) e detalhe de um protocolo. Também define o blueprint
`bp_protocolo`, compartilhado pelos controllers das famílias (NEWS2 e
protocolo composto), que registram suas rotas nele.
"""
from flask import Blueprint, request

from src.core.exceptions import BionException
from src.core.responses import json_error, json_success
from src.core.session import get_id_empresa_sessao, requer_login

from .shared.repositories.protocolo_catalogo_repository import TAMANHO_PAGINA
from .shared.services.protocolo_catalogo_service import ProtocoloCatalogoService

bp_protocolo = Blueprint("protocolo", __name__)
_svc = ProtocoloCatalogoService()


class ProtocoloController():

    @staticmethod
    @bp_protocolo.get("/")
    @requer_login
    def lista_protocolos():
        """Lista todos os protocolos cadastrados."""
        itens = _svc.listar()
        return json_success(data=[p.to_dict() for p in itens])

    @staticmethod
    @bp_protocolo.get("/catalogo")
    @requer_login
    def listar_catalogo():
        """Página de catálogo, sem filtro."""
        itens = _svc.listar_catalogo(get_id_empresa_sessao())
        return json_success(data=itens)

    @staticmethod
    @bp_protocolo.get("/catalogo/filtrar")
    @requer_login
    def listar_catalogo_filtrado():
        """Página de catálogo com filtros via query string:
        ?tipo_protocolo=escore-ponderado&escopo_populacao=adulto&escopo_uso=triagem
        &apenas_liberados=true&pagina=0"""
        itens = _svc.listar_catalogo_filtrado(
            get_id_empresa_sessao(),
            tipo_protocolo=request.args.get("tipo_protocolo"),
            escopo_populacao=request.args.get("escopo_populacao"),
            escopo_uso=request.args.get("escopo_uso"),
            apenas_liberados=request.args.get("apenas_liberados", default="false") == "true",
            offset=max(request.args.get("pagina", default=0, type=int), 0) * TAMANHO_PAGINA,
        )
        return json_success(data=itens)

    @staticmethod
    @bp_protocolo.get("/catalogo/<uuid_protocolo>")
    @requer_login
    def detalhe_catalogo(uuid_protocolo):
        """Detalhe + resumo (liberação/favoritos) + versão ativa. Aberto a
        qualquer logado: estudar um protocolo não é usá-lo."""
        try:
            dados = _svc.detalhar(uuid_protocolo, get_id_empresa_sessao())
            return json_success(data=dados)
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)
