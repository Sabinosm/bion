# protocolo_composto/controllers/protocolo_composto_controller.py
"""Rotas JSON do protocolo-composto. Espelha protocolo_escore_config_controller.py
(NEWS2) ponto a ponto -- mesmas duas rotas, mesmo formato de resposta,
mesmas decorações de autenticação/papel."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao
from .protocolo_composto_service import ProtocoloCompostoService
from ..protocolo_catalogo_controller import bp_protocolo as bp
from ..shared.services.protocolo_catalogo_service import ProtocoloCatalogoService

_svc = ProtocoloCompostoService()
_catalogo_svc = ProtocoloCatalogoService()


class ProtocoloCompostoController():

    @staticmethod
    @bp.get("/protocolo-composto/<uuid_protocolo>/campos")
    @requer_login
    def protocolo_composto_campos(uuid_protocolo):
        """Pesquisa: campos que o protocolo exige. Aberto a qualquer usuário
        logado, liberado ou não -- é estudo, não uso clínico (o gate é só na execução).
        Identificado pelo uuid do catálogo, como o resto da página."""
        try:
            catalogo = _catalogo_svc.buscar_por_uuid(uuid_protocolo)
            campos = _svc.obter_campos_para_preenchimento(catalogo.id)
            return json_success(data=[
                {"campo": c.campo, "texto": c.texto, "tipo_campo": c.tipo_campo, "opcoes": c.opcoes}
                for c in campos
            ])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/protocolo-composto/<uuid_protocolo>/composicao")
    @requer_login
    def protocolo_composto_composicao(uuid_protocolo):
        """Estrutura do composto (agregação, gatilhos, módulos e os campos de
        cada módulo). Só leitura, aberto a qualquer logado."""
        try:
            catalogo = _catalogo_svc.buscar_por_uuid(uuid_protocolo)
            return json_success(data=_svc.obter_composicao(catalogo.id))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.post("/protocolo-composto/<int:id_protocolo_catalogo>/executar")
    @requer_papel_clinico("medico", "enfermeiro")
    def protocolo_composto_executar(id_protocolo_catalogo):
        """Envio dos dados: valida liberação institucional, calcula e persiste."""
        dados = request.get_json(silent=True) or {}
        id_input = dados.get("id_input")
        respostas = dados.get("respostas", {})

        if not id_input:
            return json_error("id_input é obrigatório.", 400)

        id_empresa = get_id_empresa_sessao()
        id_usuario = get_id_usuario_sessao()

        try:
            _svc.validar_uso_permitido(id_empresa, id_protocolo_catalogo)
            execucao = _svc.executar(id_protocolo_catalogo, id_input, respostas, executor=id_usuario)
            return json_success(data=execucao.to_dict(), message="Protocolo executado e registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)