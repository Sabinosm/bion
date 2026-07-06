"""Rotas JSON do dominio Atendimento (Consultas, Triagem, Prescricao)."""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_medico_ou_enfermeiro, requer_medico
from .services import ConsultaService, AtendimentoService, PrescricaoService

bp_consulta = Blueprint("consulta", __name__)
bp_atendimento = Blueprint("atendimento", __name__)
bp_prescricao = Blueprint("prescricao", __name__)

_svc_consulta = ConsultaService()
_svc_atendimento = AtendimentoService()
_svc_prescricao = PrescricaoService()


# ==================== Consulta ====================

@bp_consulta.get("/")
@requer_login
def lista_consultas():
    apenas_abertas = request.args.get("abertas") == "true"
    itens = _svc_consulta.listar(apenas_abertas)
    return json_success(data=[c.to_dict() for c in itens])


@bp_consulta.get("/<uuid>")
@requer_login
def detalhe_consulta(uuid):
    try:
        c = _svc_consulta.buscar_por_uuid(uuid)
        return json_success(data=c.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_consulta.get("/paciente/<uuid_paciente>")
@requer_login
def consultas_do_paciente(uuid_paciente):
    from src.domains.paciente.repositories import PacienteRepository
    paciente = PacienteRepository().find_by_uuid(uuid_paciente)
    if not paciente:
        return json_error("Paciente não encontrado.", 404)
    itens = _svc_consulta.listar_por_paciente(paciente.id)
    return json_success(data=[c.to_dict() for c in itens])


@bp_consulta.post("/paciente/<uuid_paciente>")
@requer_medico_ou_enfermeiro
def abrir_consulta(uuid_paciente):
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc_consulta.abrir(uuid_paciente, dados, session["id_usuario"])
        return json_success(data=c.to_dict(), message="Consulta aberta.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_consulta.post("/<uuid>/encerrar")
@requer_medico_ou_enfermeiro
def encerrar_consulta(uuid):
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc_consulta.encerrar(uuid, dados.get("desfecho_final"), session["id_usuario"])
        return json_success(data=c.to_dict(), message="Consulta encerrada.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# ==================== Atendimento ====================

@bp_atendimento.get("/")
@requer_login
def lista_atendimentos():
    itens = _svc_atendimento.listar()
    return json_success(data=[a.to_dict() for a in itens])


@bp_atendimento.get("/<uuid>")
@requer_login
def detalhe_atendimento(uuid):
    try:
        a = _svc_atendimento.buscar_por_uuid(uuid)
        return json_success(data=a.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.get("/consulta/<uuid_consulta>")
@requer_login
def atendimentos_da_consulta(uuid_consulta):
    try:
        itens = _svc_atendimento.listar_por_consulta(uuid_consulta)
        return json_success(data=[a.to_dict() for a in itens])
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/consulta/<uuid_consulta>/abrir-triagem")
@requer_medico_ou_enfermeiro
def abrir_triagem(uuid_consulta):
    try:
        a = _svc_atendimento.abrir_triagem(uuid_consulta, session["id_usuario"])
        return json_success(data=a.to_dict(), message="Triagem aberta.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/consulta/<uuid_consulta>/abrir-avaliacao-medica")
@requer_medico
def abrir_avaliacao_medica(uuid_consulta):
    try:
        a = _svc_atendimento.abrir_avaliacao_medica(uuid_consulta, session["id_usuario"])
        return json_success(data=a.to_dict(), message="Avaliação médica aberta.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/<uuid_atendimento>/sinais-vitais")
@requer_medico_ou_enfermeiro
def registrar_sinais_vitais(uuid_atendimento):
    dados = request.get_json(silent=True) or {}
    try:
        registrados = _svc_atendimento.registrar_sinais_vitais(
            uuid_atendimento, dados.get("sinais", []), session["id_usuario"]
        )
        return json_success(
            data=[s.to_dict() for s in registrados],
            message="Sinais vitais registrados.", status=201,
        )
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/<uuid_atendimento>/coleta-clinica")
@requer_medico_ou_enfermeiro
def registrar_coleta_clinica(uuid_atendimento):
    dados = request.get_json(silent=True) or {}
    try:
        c = _svc_atendimento.registrar_coleta_clinica(uuid_atendimento, dados)
        return json_success(data=c.to_dict(), message="Coleta clínica registrada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/coleta-clinica/<uuid_coleta>/input-protocolo")
@requer_medico_ou_enfermeiro
def registrar_input_protocolo(uuid_coleta):
    """
    Registra os dados de entrada (queixa, sinais, respostas de fluxograma)
    que serão usados pelo motor de protocolo (POST /api/ia/analisar) para
    gerar o resultado da triagem/consulta.
    """
    dados = request.get_json(silent=True) or {}
    try:
        ip = _svc_atendimento.registrar_input_protocolo(uuid_coleta, dados)
        return json_success(data=ip.to_dict(), message="Input de protocolo registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_atendimento.post("/<uuid_atendimento>/finalizar")
@requer_medico_ou_enfermeiro
def finalizar_atendimento(uuid_atendimento):
    dados = request.get_json(silent=True) or {}
    try:
        a = _svc_atendimento.finalizar(uuid_atendimento, dados.get("observacoes"))
        return json_success(data=a.to_dict(), message="Atendimento finalizado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# ==================== Prescrição ====================

@bp_prescricao.post("/atendimento/<uuid_atendimento>")
@requer_medico
def registrar_resultado(uuid_atendimento):
    dados = request.get_json(silent=True) or {}
    try:
        r = _svc_prescricao.registrar_resultado(uuid_atendimento, dados, session["id_usuario"])
        return json_success(data=r.to_dict(), message="Resultado de prescrição registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_prescricao.get("/<uuid_resultado>")
@requer_login
def detalhe_resultado(uuid_resultado):
    try:
        r = _svc_prescricao.buscar_resultado_por_uuid(uuid_resultado)
        return json_success(data=r.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_prescricao.post("/<uuid_resultado>/medicamentos")
@requer_medico
def adicionar_medicamento(uuid_resultado):
    dados = request.get_json(silent=True) or {}
    try:
        p = _svc_prescricao.adicionar_medicamento(uuid_resultado, dados)
        return json_success(data=p.to_dict(), message="Medicamento prescrito.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_prescricao.post("/<uuid_resultado>/exames")
@requer_medico
def adicionar_exame(uuid_resultado):
    dados = request.get_json(silent=True) or {}
    try:
        pe = _svc_prescricao.adicionar_exame(uuid_resultado, dados)
        return json_success(data=pe.to_dict(), message="Exame prescrito.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
