"""Rotas JSON do domínio EmpresaProtocolo (liberação institucional de protocolos).

Prefixo: /v1/api/liberacao-protocolos (ver main.py). Os protocolos são
identificados pelo UUID do catálogo -- o mesmo que a página de catálogo usa;
o id numérico só aparece internamente e no registro de auditoria.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, get_id_empresa_sessao
from .empresa_protocolo_service import EmpresaProtocoloService
from src.domains.auditoria.acaoSensivel import acao_sensivel

bp = Blueprint("empresa_protocolo", __name__)
_svc = EmpresaProtocoloService()


def _auditoria(id_registro, operacao):
    return {"id_registro": id_registro, "uuid_registro": None, "operacao": operacao}


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
    @bp.put("/<uuid_protocolo>/status")
    @requer_admin
    @acao_sensivel(acao="alterar_status_protocolo", tabela="empresa_protocolo")
    def alterar_status(uuid_protocolo):
        """Body: {"ativo": bool, "politica": "obrigatorio"|"opcional" (opcional)}"""
        dados = request.get_json(silent=True) or {}
        id_empresa = get_id_empresa_sessao()
        id_registro = None  # protocolo inexistente: NOOP sem id
        try:
            id_registro = _svc.resolver_catalogo(uuid_protocolo).id_protocolo_catalogo
            vinculo = _svc.alterar_status(id_empresa, id_registro, dados)
            resposta = json_success(
                data={**vinculo.to_dict(), "uuid_protocolo": uuid_protocolo},
                message="Status do protocolo atualizado.")
            return resposta, _auditoria(id_registro, "UPDATE")
        except BionException as ex:
            return json_error(ex.message, ex.status_code), _auditoria(id_registro, "NOOP")

    @staticmethod
    @bp.put("/<uuid_protocolo>/default")
    @requer_admin
    @acao_sensivel(acao="definir_default_institucional", tabela="empresa_protocolo")
    def definir_default(uuid_protocolo):
        """Body: {"escopo": "triagem"|"consulta"|"ambos"}"""
        dados = request.get_json(silent=True) or {}
        id_empresa = get_id_empresa_sessao()
        id_registro = None
        try:
            id_registro = _svc.resolver_catalogo(uuid_protocolo).id_protocolo_catalogo
            vinculo = _svc.definir_default_institucional(id_empresa, id_registro, dados)
            resposta = json_success(
                data={**vinculo.to_dict(), "uuid_protocolo": uuid_protocolo},
                message="Protocolo padrão institucional definido.")
            return resposta, _auditoria(id_registro, "UPDATE")
        except BionException as ex:
            return json_error(ex.message, ex.status_code), _auditoria(id_registro, "NOOP")