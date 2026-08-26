"""Rotas JSON da entidade Prescricao: medicamentos prescritos."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .prescricao_service import PrescricaoService

bp_prescricao = Blueprint("prescricao", __name__)
_svc_prescricao = PrescricaoService()

class PrescricaoController():
    @staticmethod
    @bp_prescricao.post("/<uuid_resultado>/medicamentos")
    @requer_papel("medico")
    def adicionar_medicamento(uuid_resultado):
        """Adiciona um medicamento prescrito a um ResultadoPrescricao."""
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc_prescricao.adicionar_medicamento(uuid_resultado, dados)
            return json_success(data=p.to_dict(), message="Medicamento prescrito.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)