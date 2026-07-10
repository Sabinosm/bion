"""Rotas JSON do ciclo de vida do Atendimento (abertura e finalização)."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import AtendimentoService

bp_atendimento = Blueprint("atendimento", __name__)
_svc = AtendimentoService()


@bp_atendimento.get("/")
@requer_login
def lista_atendimentos():
    """Lista todos os Atendimentos cadastrados."""
    itens = _svc.listar()
    return json_success(data=[a.to_dict() for a in itens])


@bp_atendimento.get("/<uuid>")
@requer_login
def detalhe_atendimento(uuid):
    """Retorna os detalhes de um Atendimento pelo UUID."""
    try:
        a = _svc.buscar_por_uuid(uuid)
        return json_success(data=a.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.get("/consulta/<uuid_consulta>")
@requer_login
def atendimentos_da_consulta(uuid_consulta):
    """Lista os Atendimentos vinculados a uma Consulta."""
    try:
        itens = _svc.listar_por_consulta(uuid_consulta)
        return json_success(data=[a.to_dict() for a in itens])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/consulta/<uuid_consulta>/abrir-triagem")
@requer_papel("medico", "enfermeiro")
def abrir_triagem(uuid_consulta):
    """Abre um Atendimento do tipo triagem para a Consulta informada."""
    try:
        a = _svc.abrir_triagem(uuid_consulta, session["id_usuario"])
        return json_success(data=a.to_dict(), message="Triagem aberta.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/consulta/<uuid_consulta>/abrir-avaliacao-medica")
@requer_papel("medico")
def abrir_avaliacao_medica(uuid_consulta):
    """Abre um Atendimento do tipo avaliação médica para a Consulta informada."""
    try:
        a = _svc.abrir_avaliacao_medica(uuid_consulta, session["id_usuario"])
        return json_success(data=a.to_dict(), message="Avaliação médica aberta.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/<uuid_atendimento>/finalizar")
@requer_papel("medico", "enfermeiro")
def finalizar_atendimento(uuid_atendimento):
    """Finaliza um Atendimento em andamento."""
    dados = request.get_json(silent=True) or {}
    try:
        a = _svc.finalizar(uuid_atendimento, dados.get("observacoes"))
        return json_success(data=a.to_dict(), message="Atendimento finalizado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
