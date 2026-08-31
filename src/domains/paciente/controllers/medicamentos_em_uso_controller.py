"""
Rotas JSON de medicamentos em uso do paciente (parte do domínio clínico).
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_empresa_sessao
from src.domains.paciente.services import MedicamentoEmUsoService

bp = Blueprint("medicamentos_em_uso", __name__)
_svc = MedicamentoEmUsoService()

class MedicamentosEmUsoController():
    
    @staticmethod
    @bp.get("/<uuid_paciente>/medicamentos-em-uso")
    @requer_login
    def listar_medicamentos_em_uso(uuid_paciente):
        try:
            itens = _svc.listar_medicamentos_em_uso(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[m.to_dict() for m in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/medicamentos-em-uso")
    @requer_papel("medico", "enfermeiro")
    def adicionar_medicamento_em_uso(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            m = _svc.adicionar_medicamento_em_uso(uuid_paciente, dados, get_id_empresa_sessao())
            return json_success(data=m.to_dict(), message="Medicamento em uso registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)