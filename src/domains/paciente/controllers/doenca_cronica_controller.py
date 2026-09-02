"""
Rotas JSON de doenças crônicas do paciente (parte do domínio clínico).
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_empresa_sessao
from src.domains.paciente.services import DoencaCronicaService

bp = Blueprint("doencas-cronicas", __name__)
_svc = DoencaCronicaService()



class DoencaCronicaController():

    @staticmethod
    @bp.get("/<uuid_paciente>/doencas-cronicas")
    @requer_login
    def listar_doencas(uuid_paciente):
        try:
            itens = _svc.listar_doencas(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[d.to_dict() for d in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/doencas-cronicas")
    @requer_papel("medico", "enfermeiro")
    def adicionar_doenca(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.adicionar_doenca(uuid_paciente, dados, get_id_empresa_sessao())
            return json_success(data=d.to_dict(), message="Doença crônica registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: corrige/atualiza uma doença crônica já registrada.
    @staticmethod
    @bp.put("/<uuid_paciente>/doencas-cronicas/<uuid_doenca>")
    @requer_papel("medico", "enfermeiro")
    def atualizar_doenca(uuid_paciente, uuid_doenca):
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.atualizar_doenca(uuid_paciente, uuid_doenca, dados, get_id_empresa_sessao())
            return json_success(data=d.to_dict(), message="Doença crônica atualizada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)