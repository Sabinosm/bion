"""Rotas JSON da entidade Prescrição: resultado clínico, medicamentos e exames."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import PrescricaoService

bp_prescricao = Blueprint("prescricao", __name__)
_svc_prescricao = PrescricaoService()


@bp_prescricao.post("/atendimento/<uuid_atendimento>")
@requer_papel("medico")
def registrar_resultado(uuid_atendimento):
    """Registra o diagnóstico (CID-10) e desfecho de um Atendimento."""
    dados = request.get_json(silent=True) or {}
    try:
        r = _svc_prescricao.registrar_resultado(uuid_atendimento, dados, session["id_usuario"])
        return json_success(data=r.to_dict(), message="Resultado de prescrição registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_prescricao.get("/<uuid_resultado>")
@requer_login
def detalhe_resultado(uuid_resultado):
    """Retorna os detalhes de um ResultadoPrescricao pelo UUID."""
    try:
        r = _svc_prescricao.buscar_resultado_por_uuid(uuid_resultado)
        return json_success(data=r.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


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


@bp_prescricao.post("/<uuid_resultado>/exames")
@requer_papel("medico")
def adicionar_exame(uuid_resultado):
    """Adiciona um exame prescrito a um ResultadoPrescricao."""
    dados = request.get_json(silent=True) or {}
    try:
        pe = _svc_prescricao.adicionar_exame(uuid_resultado, dados)
        return json_success(data=pe.to_dict(), message="Exame prescrito.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
