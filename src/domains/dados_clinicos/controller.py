"""Rotas JSON do registro de dados clínicos: sinais vitais, coleta clínica e input de protocolo."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_papel, session
from .service import DadosClinicosService

bp_dados_clinicos = Blueprint("dados_clinicos", __name__)
_svc_dados_clinicos = DadosClinicosService()


@bp_dados_clinicos.post("/<uuid_atendimento>/sinais-vitais")
@requer_papel("medico", "enfermeiro")
def registrar_sinais_vitais(uuid_atendimento):
    """Registra um ou mais sinais vitais para o Atendimento informado."""
    dados = request.get_json(silent=True) or {}
    try:
        registrados = _svc_dados_clinicos.registrar_sinais_vitais(
            uuid_atendimento, dados.get("sinais", []), session["id_usuario"]
        )
        return json_success(
            data=[s.to_dict() for s in registrados],
            message="Sinais vitais registrados.", status=201,
        )
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_dados_clinicos.post("/<uuid_atendimento>/coleta-clinica")
@requer_papel("medico", "enfermeiro")
def registrar_coleta_clinica(uuid_atendimento):
    """Cria uma coleta clínica para o Atendimento informado."""
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc_dados_clinicos.registrar_coleta_clinica(uuid_atendimento, dados)
        return json_success(data=c.to_dict(), message="Coleta clínica registrada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_dados_clinicos.post("/coleta-clinica/<uuid_coleta>/input-protocolo")
@requer_papel("medico", "enfermeiro")
def registrar_input_protocolo(uuid_coleta):
    """Registra o input de protocolo (queixa, sinais, fluxograma) de uma coleta clínica."""
    dados = request.get_json(silent=True) or {}
    try:
        ip = _svc_dados_clinicos.registrar_input_protocolo(uuid_coleta, dados)
        return json_success(data=ip.to_dict(), message="Input de protocolo registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
