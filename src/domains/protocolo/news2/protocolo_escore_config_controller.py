"""protocolo_escore_config_controller.py

Rotas JSON do NEWS2 (escore ponderado): consulta dos campos que o protocolo
exige e execução com persistência do resultado. Todas identificam o protocolo
pelo UUID do catálogo e só aceitam protocolos do tipo escore ponderado. Registra
as rotas no blueprint compartilhado do catálogo de protocolos.
"""
from flask import request

from src.core.exceptions import BionException
from src.core.responses import json_error, json_success
from src.core.session import get_id_empresa_sessao, get_id_usuario_sessao, requer_login, requer_papel_clinico

from ..protocolo_catalogo_controller import bp_protocolo as bp
from ..shared.schemas.schema_execucao import parse_execucao_request
from ..shared.services.protocolo_catalogo_service import ProtocoloCatalogoService
from .protocolo_escore_config_service import News2Service
from .protocolo_escore_ponderado import EscorePonderadoStrategy

TIPO_PROTOCOLO = EscorePonderadoStrategy.TIPO_PROTOCOLO

_svc = News2Service()
_catalogo_svc = ProtocoloCatalogoService()


class News2Controller():

    @staticmethod
    @bp.get("/news2/<uuid_protocolo>/campos")
    @requer_login
    def news2_campos(uuid_protocolo):
        """Campos que o protocolo exige. Aberto a qualquer usuário logado,
        liberado ou não: é estudo, não uso clínico (o gate fica na execução)."""
        try:
            catalogo = _catalogo_svc.buscar_por_uuid_e_tipo(uuid_protocolo, TIPO_PROTOCOLO)
            campos = _svc.obter_campos_para_preenchimento(catalogo.id)
            return json_success(data=[
                {"campo": c.campo, "texto": c.texto, "tipo_campo": c.tipo_campo, "opcoes": c.opcoes}
                for c in campos
            ])
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp.post("/news2/<uuid_protocolo>/executar")
    @requer_papel_clinico("medico", "enfermeiro")
    def news2_executar(uuid_protocolo):
        """Valida a liberação institucional, calcula e persiste a execução."""
        try:
            requisicao = parse_execucao_request(request.get_json(silent=True))
            catalogo = _catalogo_svc.buscar_por_uuid_e_tipo(uuid_protocolo, TIPO_PROTOCOLO)
            _svc.validar_uso_permitido(get_id_empresa_sessao(), catalogo.id)
            execucao = _svc.executar(
                catalogo.id, requisicao.id_input, requisicao.respostas, executor=get_id_usuario_sessao()
            )
            return json_success(data=execucao.to_dict(), message="Protocolo executado e registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)
