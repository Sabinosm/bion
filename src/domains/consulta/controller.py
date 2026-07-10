"""Rotas JSON da entidade Consulta."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import ConsultaService

bp_consulta = Blueprint("consulta", __name__)
_svc = ConsultaService()


@bp_consulta.get("/")
@requer_login
def lista_consultas():
    """Lista Consultas. Aceita ?abertas=true para filtrar as não encerradas."""
    apenas_abertas = request.args.get("abertas") == "true"
    itens = _svc.listar(apenas_abertas)
    return json_success(data=[c.to_dict() for c in itens])


@bp_consulta.get("/<uuid>")
@requer_login
def detalhe_consulta(uuid):
    """Retorna os detalhes de uma Consulta pelo UUID."""
    try:
        c = _svc.buscar_por_uuid(uuid)
        return json_success(data=c.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_consulta.get("/paciente/<uuid_paciente>")
@requer_login
def consultas_do_paciente(uuid_paciente):
    """Lista o histórico de Consultas de um paciente."""
    from src.domains.paciente.repositories import PacienteRepository
    paciente = PacienteRepository().find_by_uuid(uuid_paciente)
    if not paciente:
        return json_error("Paciente não encontrado.", 404)
    itens = _svc.listar_por_paciente(paciente.id)
    return json_success(data=[c.to_dict() for c in itens])


@bp_consulta.post("/paciente/<uuid_paciente>")
@requer_papel("medico", "enfermeiro")
def abrir_consulta(uuid_paciente):
    """Abre uma nova Consulta para o paciente informado."""
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc.abrir(uuid_paciente, dados, session["id_usuario"])
        return json_success(data=c.to_dict(), message="Consulta aberta.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_consulta.post("/<uuid>/encerrar")
@requer_papel("medico", "enfermeiro")
def encerrar_consulta(uuid):
    """Encerra uma Consulta em aberto com o desfecho final informado."""
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc.encerrar(uuid, dados.get("desfecho_final"), session["id_usuario"])
        return json_success(data=c.to_dict(), message="Consulta encerrada.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
