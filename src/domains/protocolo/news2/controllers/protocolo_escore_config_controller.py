"""Rotas JSON de execução do protocolo NEWS2."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao
from src.core.session.sessaoAutenticacao import requer_login
from ..services.protocolo_escore_config_service import News2Service

bp = Blueprint("news2", __name__)
_svc = News2Service()


class News2Controller():

    @staticmethod
    @bp.post("/<int:id_protocolo_catalogo>/executar")
    @requer_papel_clinico("medico", "enfermeiro")
    def executar(id_protocolo_catalogo):
        """Executa o NEWS2 sobre um Input_Protocolo já existente, validando
        a cascata empresa -> configuração pessoal antes de calcular e persistir."""
        dados = request.get_json(silent=True) or {}
        id_input = dados.get("id_input")
        respostas = dados.get("respostas", {})

        if not id_input:
            return json_error("id_input é obrigatório.", 400)

        id_empresa = get_id_empresa_sessao()
        id_usuario = get_id_usuario_sessao()

        try:
            _svc.validar_uso_permitido(id_empresa, id_usuario, id_protocolo_catalogo)
            execucao = _svc.executar(id_protocolo_catalogo, id_input, respostas, executor=id_usuario)
            return json_success(data=execucao.to_dict(), message="Protocolo executado e registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
        
    @staticmethod
    @bp.get("/<int:id_protocolo_catalogo>/campos")
    @requer_login
    def campos(id_protocolo_catalogo):
        """Pesquisa: retorna os campos que o protocolo exige, se a empresa o liberou.
        Não exige papel clínico -- qualquer usuário logado pode estudar o protocolo."""
        id_empresa = get_id_empresa_sessao()
        try:
            campos = _svc.obter_campos_para_preenchimento(id_empresa, id_protocolo_catalogo)
            return json_success(data=[
                {"campo": c.campo, "texto": c.texto, "tipo_campo": c.tipo_campo, "opcoes": c.opcoes}
                for c in campos
            ])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)