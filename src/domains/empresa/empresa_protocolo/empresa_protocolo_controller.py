"""
empresa_protocolo_controller.py

Camada HTTP da liberação institucional de protocolos. Cada empresa decide quais
protocolos do catálogo estão liberados, se são obrigatórios ou opcionais e qual
é o padrão institucional por escopo de uso. As rotas ficam sob o prefixo
/v1/api/liberacao-protocolos (registrado no main.py) e identificam o protocolo
pelo UUID do catálogo, o mesmo usado pela página de catálogo; o id numérico só
circula internamente e no registro de auditoria. A listagem exige admin; as
alterações são governança clínica, exigem super admin e são auditadas como
ação sensível, inclusive as tentativas que falham (operação NOOP).
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, requer_super_admin, get_id_empresa_sessao
from .empresa_protocolo_service import EmpresaProtocoloService
from src.domains.auditoria.acaoSensivel import acao_sensivel

bp = Blueprint("empresa_protocolo", __name__)
_svc = EmpresaProtocoloService()


def _auditoria(id_registro, operacao, uuid_registro):
    """Metadados de auditoria da ação. id_registro é o id do protocolo do catálogo; uuid_registro não é preenchido."""
    return {"id_registro": id_registro, "uuid_registro": uuid_registro, "operacao": operacao}


def _serializar_item(item: dict) -> dict:
    """Protocolo do catálogo + estado do vínculo (protocolo nunca tocado = não liberado)."""
    vinculo = item["vinculo"]
    return {
        "protocolo": item["protocolo"].to_dict(),
        "ativo": vinculo.ativo if vinculo else False,
        "politica": vinculo.politica if vinculo else None,
        "escopo_default_institucional": vinculo.escopo_default_institucional if vinculo else None,
    }


class EmpresaProtocoloController:

    @staticmethod
    @bp.get("/")
    @requer_admin
    def listar():
        """Lista o estado de todos os protocolos do catálogo em relação à empresa logada."""
        itens = _svc.listar_para_empresa(get_id_empresa_sessao())
        return json_success(data=[_serializar_item(item) for item in itens])

    @staticmethod
    @bp.put("/<uuid_protocolo>/status")
    @requer_super_admin
    @acao_sensivel(acao="alterar_status_protocolo", tabela="empresa_protocolo")
    def alterar_status(uuid_protocolo):
        """Libera/bloqueia um protocolo e/ou muda sua política.

        Body: {"ativo": bool, "politica": "obrigatorio"|"opcional" (opcional)}
        """
        dados = request.get_json(silent=True) or {}
        id_empresa = get_id_empresa_sessao()
        id_registro = None  # protocolo inexistente: NOOP sem id
        try:
            catalogo = _svc.resolver_catalogo(uuid_protocolo)
            id_registro = catalogo.id
            uuid_registro = catalogo.uuid
            vinculo = _svc.alterar_status(id_empresa, catalogo, dados)
            resposta = json_success(
                data={**vinculo.to_dict(), "uuid_protocolo": uuid_protocolo},
                message="Status do protocolo atualizado.")
            return resposta, _auditoria(id_registro, "UPDATE", uuid_registro=uuid_registro)
        except BionException as ex:
            return json_error(ex.message, ex.status_code), _auditoria(id_registro, "NOOP")

    @staticmethod
    @bp.put("/<uuid_protocolo>/default")
    @requer_super_admin
    @acao_sensivel(acao="definir_default_institucional", tabela="empresa_protocolo")
    def definir_default(uuid_protocolo):
        """Define o protocolo como padrão institucional de um escopo.

        Body: {"escopo": "triagem"|"consulta"|"ambos"}
        """
        dados = request.get_json(silent=True) or {}
        id_empresa = get_id_empresa_sessao()
        id_registro = None  # protocolo inexistente: NOOP sem id
        try:
            catalogo = _svc.resolver_catalogo(uuid_protocolo)
            id_registro = catalogo.id
            uuid_registro = catalogo.uuid
            vinculo = _svc.definir_default_institucional(id_empresa, catalogo, dados)
            resposta = json_success(
                data={**vinculo.to_dict(), "uuid_protocolo": uuid_protocolo},
                message="Protocolo padrão institucional definido.")
            return resposta, _auditoria(id_registro, "UPDATE", uuid_registro=uuid_registro)
        except BionException as ex:
            return json_error(ex.message, ex.status_code), _auditoria(id_registro, "NOOP")