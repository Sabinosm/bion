"""Rotas JSON da entidade ResultadoPrescricao: diagnóstico e desfecho clínico."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_usuario_sessao
from .resultado_prescricao_service import ResultadoPrescricaoService

bp_resultado_prescricao = Blueprint("resultado_prescricao", __name__)
_svc_resultado = ResultadoPrescricaoService()

class ResultadoPrescricaoController():
    
    @staticmethod
    @bp_resultado_prescricao.post("/atendimento/<uuid_atendimento>")
    @requer_papel("medico")
    def registrar_resultado(uuid_atendimento):
        """Registra o diagnóstico (CID-10) e desfecho de um Atendimento."""
        dados = request.get_json(silent=True) or {}
        try:
            r = _svc_resultado.registrar_resultado(uuid_atendimento, dados, get_id_usuario_sessao())
            return json_success(data=r.to_dict(), message="Resultado de prescrição registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_resultado_prescricao.get("/<uuid_resultado>")
    @requer_login
    def detalhe_resultado(uuid_resultado):
        """Retorna os detalhes de um ResultadoPrescricao pelo UUID."""
        try:
            r = _svc_resultado.buscar_resultado_por_uuid(uuid_resultado)
            return json_success(data=r.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)