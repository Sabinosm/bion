"""
Rotas JSON de dados cadastrais do paciente (Paciente + PacienteDadosPessoais).

ADICIONADO: duas rotas para tipo_sanguineo, refletindo a separação
decidida (registrar = novo exame/histórico; corrigir = editar um
registro específico por engano de digitação). Antes isso era só um
campo dentro do PUT geral de atualizar(); agora tem semântica própria.

PII (nome, cpf, telefone, email, endereco) so e devolvida em texto claro
para medico/enfermeiro; qualquer outro perfil autenticado ve apenas os
dados clinicos nao-identificaveis do Paciente.

ALTERADO: toda rota agora passa id_empresa (da sessão do usuário
logado) pro service. Sem isso, listar()/buscar_por_uuid()/etc. não têm
como saber de qual empresa filtrar -- e um usuário logado conseguiria
ver ou editar pacientes de OUTRA empresa, já que o UUID sozinho não
prova posse (falha de isolamento de tenant / IDOR).
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_usuario_sessao, get_id_empresa_sessao
from src.domains.paciente.services import PacienteService

bp = Blueprint("paciente_pessoal", __name__)
_svc = PacienteService()


def _serializar(paciente, com_pii: bool):
    d = paciente.to_dict()
    if com_pii:
        d["pessoal"] = _svc.dados_pessoais_descriptografados(paciente)
    return d

class PacientePessoalController():
    
    @staticmethod
    @bp.get("/")
    @requer_login
    def lista():
        com_pii = session.get("tipo_usuario") in ("medico", "enfermeiro")
        pacientes = _svc.listar(get_id_empresa_sessao())
        return json_success(data=[_serializar(p, com_pii) for p in pacientes])


    @staticmethod
    @bp.get("/<uuid>")
    @requer_login
    def detalhe(uuid):
        com_pii = session.get("tipo_usuario") in ("medico", "enfermeiro")
        try:
            p = _svc.buscar_por_uuid(uuid, get_id_empresa_sessao())
            return json_success(data=_serializar(p, com_pii))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/")
    @requer_papel("medico", "enfermeiro")
    def cadastrar():
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc.cadastrar(dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Paciente cadastrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.put("/<uuid>")
    @requer_papel("medico", "enfermeiro")
    def atualizar(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc.atualizar(uuid, dados, get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Paciente atualizado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: exercício do direito ao esquecimento (LGPD) -- remove
    # PacienteDadosPessoais mantendo o registro clínico anonimizado
    @staticmethod
    @bp.post("/<uuid>/anonimizar")
    @requer_papel("admin", "medico")
    def anonimizar(uuid):
        try:
            p = _svc.anonimizar(uuid, get_id_empresa_sessao())
            return json_success(data=p.to_dict(), message="Paciente anonimizado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: registra novo exame/resultado de tipo sanguíneo (preserva histórico)
    @staticmethod
    @bp.post("/<uuid>/tipo-sanguineo")
    @requer_papel("medico", "enfermeiro")
    def registrar_tipo_sanguineo(uuid):
        dados = request.get_json(silent=True) or {}
        if not dados.get("tipo_sanguineo"):
            return json_error("tipo_sanguineo é obrigatório.", 422)
        try:
            p = _svc.registrar_tipo_sanguineo(uuid, dados["tipo_sanguineo"], get_id_usuario_sessao())
            return json_success(data=_serializar(p, True), message="Tipo sanguíneo registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: corrige uma observação específica (erro de digitação, não novo exame)
    @staticmethod
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
    @staticmethod
    @bp.delete("/tipo-sanguineo/<uuid_observacao>")
    @requer_papel("admin", "medico")
    def remover_tipo_sanguineo(uuid_observacao):
        try:
            _svc.remover_tipo_sanguineo(uuid_observacao)
            return json_success(message="Observação de tipo sanguíneo removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)