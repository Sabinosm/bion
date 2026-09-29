"""Rotas JSON do dominio Configuracao (preferencias por usuario)."""

from flask import Blueprint, request, g

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico
from .service import ConfiguracaoService

bp = Blueprint("configuracao", __name__)
_svc = ConfiguracaoService()

class ConfiguracaoController():
    
    @staticmethod
    @bp.get("/")
    @requer_login
    def minha_configuracao():
        cfg = _svc.obter_ou_criar(g.id_usuario)
        return json_success(data={ "configuracoes": cfg.to_dict()})


    @staticmethod
    @bp.put("/")
    @requer_login
    def atualizar():
        dados = request.get_json(silent=True) or {}
        try:
            cfg = _svc.atualizar(g.id_usuario, dados.get("configuracoes", {}))
            return json_success(data={ "configuracoes": cfg.to_dict()}, message="Configurações atualizadas.")
        
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Protocolos: identificados pelo UUID do catálogo (string), o mesmo que
    # a página de catálogo já usa. O id numérico não sai do back.
    # Prefixo real do blueprint: /v1/api/configuracoes (ver main.py).

    @staticmethod
    @bp.get("/protocolos/default")
    @requer_papel_clinico("medico", "enfermeiro")
    def default_efetivo():
        """?escopo=triagem|consulta|ambos -- o protocolo que a consulta carrega
        por padrão (pessoal > institucional > primeiro liberado)."""
        try:
            catalogo, origem = _svc.resolver_default(g.id_usuario, request.args.get("escopo"))
            return json_success(data={
                "protocolo": {
                    "uuid": catalogo.uuid,
                    "nome_protocolo": catalogo.nome_protocolo,
                    "sigla": catalogo.sigla,
                    "escopo_uso": catalogo.escopo_uso,
                },
                "origem": origem,
            })
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/protocolos")
    @requer_papel_clinico("medico", "enfermeiro")
    def listar_protocolos():
        # Cada item traz uuid, sigla, em_uso e escopo_default -- é o que a
        # página de catálogo cruza com os cards para pintar a estrela.
        protocolos = _svc.listar_protocolos(g.id_usuario)
        return json_success(data=[p.to_dict() for p in protocolos])


    @staticmethod
    @bp.put("/protocolos/<uuid_protocolo>/habilitar")
    @requer_papel_clinico("medico", "enfermeiro")
    def habilitar_protocolo(uuid_protocolo):
        try:
            protocolo = _svc.habilitar_protocolo(g.id_usuario, uuid_protocolo)
            return json_success(data=protocolo.to_dict(), message="Protocolo habilitado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.put("/protocolos/<uuid_protocolo>/desabilitar")
    @requer_papel_clinico("medico", "enfermeiro")
    def desabilitar_protocolo(uuid_protocolo):
        try:
            protocolo = _svc.desabilitar_protocolo(g.id_usuario, uuid_protocolo)
            return json_success(data=protocolo.to_dict(), message="Protocolo desabilitado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.put("/protocolos/<uuid_protocolo>/default")
    @requer_papel_clinico("medico", "enfermeiro")
    def definir_default(uuid_protocolo):
        """Body: {"escopo": "triagem" | "consulta" | "ambos"}"""
        dados = request.get_json(silent=True) or {}
        try:
            protocolo = _svc.definir_default_pessoal(
                g.id_usuario, uuid_protocolo, dados.get("escopo")
            )
            return json_success(data=protocolo.to_dict(), message="Protocolo definido como padrão.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.delete("/protocolos/<uuid_protocolo>/default")
    @requer_papel_clinico("medico", "enfermeiro")
    def remover_default(uuid_protocolo):
        try:
            protocolo = _svc.remover_default_pessoal(g.id_usuario, uuid_protocolo)
            return json_success(data=protocolo.to_dict(), message="Padrão pessoal removido; vale o padrão da instituição.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)