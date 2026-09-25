"""Rotas JSON do domínio EmpresaProtocolo (liberação institucional de protocolos)."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, get_id_empresa_sessao
from .empresa_protocolo_service import EmpresaProtocoloService
from src.domains.auditoria.acaoSensivel import acao_sensivel

bp = Blueprint("empresa_protocolo", __name__)
_svc = EmpresaProtocoloService()


class EmpresaProtocoloController():

    @staticmethod
    @bp.get("/")
    @requer_admin
    def listar():
        """Lista o estado de todos os protocolos do catálogo em relação à empresa logada."""
        itens = _svc.listar_para_empresa(get_id_empresa_sessao())
        return json_success(data=[
            {
                "protocolo": item["protocolo"].to_dict(),
                "ativo": item["vinculo"].ativo if item["vinculo"] else False,
                "politica": item["vinculo"].politica if item["vinculo"] else None,
                "escopo_default_institucional": item["vinculo"].escopo_default_institucional if item["vinculo"] else None,
            }
            for item in itens
        ])

    @staticmethod
    @bp.put("/<int:id_protocolo_catalogo>/status")
    @requer_admin
    @acao_sensivel(acao="alterar_status_protocolo", tabela="empresa_protocolo")
    def alterar_status(id_protocolo_catalogo):
        dados = request.get_json(silent=True) or {}
        id_empresa = get_id_empresa_sessao()
        try:
            vinculo = _svc.alterar_status(id_empresa, id_protocolo_catalogo, dados)
            resposta = json_success(data=vinculo.to_dict(), message="Status do protocolo atualizado.")
            return resposta, {
                "id_registro": id_protocolo_catalogo,
                "uuid_registro": None,
                "operacao": "UPDATE",
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": id_protocolo_catalogo, "uuid_registro": None, "operacao": "NOOP"}

    @staticmethod
    @bp.put("/<int:id_protocolo_catalogo>/default")
    @requer_admin
    @acao_sensivel(acao="definir_default_institucional", tabela="empresa_protocolo")
    def definir_default(id_protocolo_catalogo):
        dados = request.get_json(silent=True) or {}
        id_empresa = get_id_empresa_sessao()
        try:
            vinculo = _svc.definir_default_institucional(id_empresa, id_protocolo_catalogo, dados)
            resposta = json_success(data=vinculo.to_dict(), message="Protocolo padrão institucional definido.")
            return resposta, {
                "id_registro": id_protocolo_catalogo,
                "uuid_registro": None,
                "operacao": "UPDATE",
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": id_protocolo_catalogo, "uuid_registro": None, "operacao": "NOOP"}