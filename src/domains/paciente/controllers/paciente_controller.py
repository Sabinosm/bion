"""
Rotas JSON de dados cadastrais do paciente (Paciente + PacienteDadosPessoais).

ADICIONADO: duas rotas para tipo_sanguineo, refletindo a separação
decidida (registrar = novo exame/histórico; corrigir = editar um
registro específico por engano de digitação). Antes isso era só um
campo dentro do PUT geral de atualizar(); agora tem semântica própria.

PII (nome, cpf, telefone, email, endereco) so e devolvida em texto claro
para medico/enfermeiro; qualquer outro perfil autenticado ve apenas os
dados clinicos nao-identificaveis do Paciente.
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from src.domains.paciente.services import PacienteService

bp = Blueprint("paciente_pessoal", __name__)
_svc = PacienteService()


def _serializar(paciente, com_pii: bool):
    d = paciente.to_dict()
    if com_pii:
        d["pessoal"] = _svc.dados_pessoais_descriptografados(paciente)
    return d


@bp.get("/")
@requer_login
def lista():
    com_pii = session.get("tipo_usuario") in ("medico", "enfermeiro")
    pacientes = _svc.listar()
    return json_success(data=[_serializar(p, com_pii) for p in pacientes])


@bp.get("/<uuid>")
@requer_login
def detalhe(uuid):
    com_pii = session.get("tipo_usuario") in ("medico", "enfermeiro")
    try:
        p = _svc.buscar_por_uuid(uuid)
        return json_success(data=_serializar(p, com_pii))
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/")
@requer_papel("medico", "enfermeiro")
def cadastrar():
    dados = request.get_json(silent=True) or {}
    try:
        p = _svc.cadastrar(dados, session["id_usuario"])
        return json_success(data=_serializar(p, True), message="Paciente cadastrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.put("/<uuid>")
@requer_papel("medico", "enfermeiro")
def atualizar(uuid):
    dados = request.get_json(silent=True) or {}
    try:
        p = _svc.atualizar(uuid, dados)
        return json_success(data=_serializar(p, True), message="Paciente atualizado.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# NOVO: registra novo exame/resultado de tipo sanguíneo (preserva histórico)
@bp.post("/<uuid>/tipo-sanguineo")
@requer_papel("medico", "enfermeiro")
def registrar_tipo_sanguineo(uuid):
    dados = request.get_json(silent=True) or {}
    if not dados.get("tipo_sanguineo"):
        return json_error("tipo_sanguineo é obrigatório.", 422)
    try:
        p = _svc.registrar_tipo_sanguineo(uuid, dados["tipo_sanguineo"], session["id_usuario"])
        return json_success(data=_serializar(p, True), message="Tipo sanguíneo registrado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# NOVO: corrige uma observação específica (erro de digitação, não novo exame)
@bp.put("/tipo-sanguineo/<uuid_observacao>")
@requer_papel("medico", "enfermeiro")
def corrigir_tipo_sanguineo(uuid_observacao):
    dados = request.get_json(silent=True) or {}
    if not dados.get("tipo_sanguineo"):
        return json_error("tipo_sanguineo é obrigatório.", 422)
    try:
        obs = _svc.corrigir_tipo_sanguineo(uuid_observacao, dados["tipo_sanguineo"])
        return json_success(data=obs.to_dict(), message="Tipo sanguíneo corrigido.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# NOVO: remove um registro criado por engano (ex: paciente errado, duplicata)
@bp.delete("/tipo-sanguineo/<uuid_observacao>")
@requer_papel("admin", "medico")
def remover_tipo_sanguineo(uuid_observacao):
    try:
        _svc.remover_tipo_sanguineo(uuid_observacao)
        return json_success(message="Observação de tipo sanguíneo removida.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    
