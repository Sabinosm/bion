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

    # NOVO: soft delete -- remove uma doença crônica já registrada.
    # Motivo vem no corpo da requisição (DELETE com body é incomum mas
    # válido em HTTP/REST; alternativa seria query string, mas body
    # mantém consistência com os outros schemas Pydantic do domínio).
    @staticmethod
    @bp.delete("/<uuid_paciente>/doencas-cronicas/<uuid_doenca>")
    @requer_papel("medico", "enfermeiro")
    def remover_doenca(uuid_paciente, uuid_doenca):
        dados = request.get_json(silent=True) or {}
        try:
            _svc.remover_doenca(uuid_paciente, uuid_doenca, dados, get_id_empresa_sessao())
            return json_success(message="Doença crônica removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # NOVO: reverte um soft delete. POST (não PUT) porque é uma ação,
    # não uma substituição de estado do recurso via corpo -- não tem
    # payload, só o efeito colateral de reverter deletado/deletado_em/
    # motivo_delete/observacoes_delete.
    @staticmethod
    @bp.post("/<uuid_paciente>/doencas-cronicas/<uuid_doenca>/restaurar")
    @requer_papel("medico", "enfermeiro")
    def restaurar_doenca(uuid_paciente, uuid_doenca):
        try:
            d = _svc.restaurar_doenca(uuid_paciente, uuid_doenca, get_id_empresa_sessao())
            return json_success(data=d.to_dict(), message="Doença crônica restaurada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)