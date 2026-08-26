"""
Rotas JSON de dados clinicos do paciente: alergias, doencas cronicas e
medicamentos em uso.

ADICIONADO: rota de nova reação numa alergia já existente (capacidade
nova, antes o schema só suportava uma reação por alergia).
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from src.domains.paciente.services import AlergiaService

bp = Blueprint("alergia", __name__)
_svc = AlergiaService()


class AlergiaController():

    @staticmethod
    @bp.get("/<uuid_paciente>/alergias")
    @requer_login
    def listar_alergias(uuid_paciente):
        try:
            itens = _svc.listar_alergias(uuid_paciente)
            return json_success(data=[a.to_dict() for a in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/alergias")
    @requer_papel("medico", "enfermeiro")
    def adicionar_alergia(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc.adicionar_alergia(uuid_paciente, dados)
            return json_success(data=a.to_dict(), message="Alergia registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: registra uma reação adicional numa alergia já existente
    @staticmethod
    @bp.post("/alergias/<uuid_alergia>/reacoes")
    @requer_papel("medico", "enfermeiro")
    def adicionar_reacao(uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc.adicionar_reacao(uuid_alergia, dados)
            return json_success(data=a.to_dict(), message="Reação registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: remove a alergia inteira (com todo o histórico de reações)
    @staticmethod
    @bp.delete("/alergias/<uuid_alergia>")
    @requer_papel("admin", "medico")
    def remover_alergia(uuid_alergia):
        try:
            _svc.remover_alergia(uuid_alergia)
            return json_success(message="Alergia removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: remove apenas uma reação específica, mantendo a alergia e o
    # restante do histórico intactos
    @staticmethod
    @bp.delete("/alergias/reacoes/<uuid_reacao>")
    @requer_papel("admin", "medico")
    def remover_reacao(uuid_reacao):
        try:
            _svc.remover_reacao(uuid_reacao)
            return json_success(message="Reação removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


