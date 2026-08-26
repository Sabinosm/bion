"""Rotas JSON da entidade PrescricaoExame: exames prescritos."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .prescricao_exame_service import PrescricaoExameService

bp_prescricao_exame = Blueprint("prescricao_exame", __name__)
_svc_prescricao_exame = PrescricaoExameService()

class PrescricaoExameController():
    
    @staticmethod
    @bp_prescricao_exame.post("/<uuid_resultado>/exames")
    @requer_papel("medico")
    def adicionar_exame(uuid_resultado):
        """Adiciona um exame prescrito a um ResultadoPrescricao."""
        dados = request.get_json(silent=True) or {}
        try:
            pe = _svc_prescricao_exame.adicionar_exame(uuid_resultado, dados)
            return json_success(data=pe.to_dict(), message="Exame prescrito.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)