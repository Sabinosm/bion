"""Rotas JSON da entidade Consulta.

Permissões: eixo clínico, por NÍVEL MÍNIMO (ver src/core/papeis.py).
"enfermeiro" já inclui médico (superset). is_admin não entra aqui.
Toda rota passa id_empresa da sessão -- UUID sozinho não prova posse.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_papel_clinico, get_id_usuario_sessao, get_id_empresa_sessao
from src.domains.auditoria.acaoSensivel import acesso_auditado
from .service import ConsultaService

bp_consulta = Blueprint("consulta", __name__)
_svc = ConsultaService()


def _meta_update(c, campo, justificativa=None):
    return {
        "id_registro": c.id,
        "uuid_registro": c.uuid,
        "operacao": "UPDATE",
        "campo_alterado": campo,
        "justificativa": justificativa,
    }


class ConsultasController():

    @staticmethod
    @bp_consulta.get("/")
    @requer_papel_clinico("enfermeiro","medico")
    def lista_consultas():
        """?abertas=true filtra as não encerradas."""
        apenas_abertas = request.args.get("abertas") == "true"
        itens = _svc.listar(get_id_empresa_sessao(), apenas_abertas)
        return json_success(data=[c.to_dict() for c in itens])

    @staticmethod
    @bp_consulta.get("/<uuid>")
    @requer_papel_clinico("enfermeiro","medico")
    @acesso_auditado(recurso="visualizar consulta", operacao="leitura")
    def detalhe_consulta(uuid):
        try:
            return json_success(data=_svc.buscar_por_uuid(uuid, get_id_empresa_sessao()).to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_consulta.get("/paciente/<uuid_paciente>")
    @requer_papel_clinico("enfermeiro","medico")
    @acesso_auditado(recurso="historico de consultas do paciente", operacao="leitura")
    def consultas_do_paciente(uuid_paciente):
        try:
            itens = _svc.listar_por_paciente(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[c.to_dict() for c in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # ---- abertura: uma rota, três formas de corpo (ver ConsultaService.abrir)
    @staticmethod
    @bp_consulta.post("/")
    @requer_papel_clinico("enfermeiro","medico")
    def abrir_consulta():
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.abrir(dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=c.to_dict(), message="Consulta aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # Compatibilidade com o front atual: atalho para {"uuid_paciente": ...}
    @staticmethod
    @bp_consulta.post("/paciente/<uuid_paciente>")
    @requer_papel_clinico("enfermeiro","medico")
    def abrir_consulta_paciente(uuid_paciente):
        dados = dict(request.get_json(silent=True) or {})
        dados["uuid_paciente"] = uuid_paciente
        try:
            c = _svc.abrir(dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=c.to_dict(), message="Consulta aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # ---- encerramento: step-up + log atômico (service com commit=False)
    @staticmethod
    @bp_consulta.post("/<uuid>/encerrar")
    @requer_papel_clinico("enfermeiro","medico")
    @acesso_auditado(recurso="encerrar_consulta", operacao="escrita")
    def encerrar_consulta(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.encerrar(uuid, dados.get("desfecho_final"), get_id_usuario_sessao(),
                              get_id_empresa_sessao(), commit=False)
            resposta = json_success(data=c.to_dict(), message="Consulta encerrada.")
            return resposta, _meta_update(c, "status_consulta", dados.get("justificativa"))
        except BionException as ex:
            return json_error(ex.message, ex.status_code), {
                "id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}

    @staticmethod
    @bp_consulta.post("/<uuid>/evadir")
    @requer_papel_clinico("enfermeiro","medico")
    @acesso_auditado(recurso="evasao_consulta", operacao="escrita")
    def evadir_consulta(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.evadir(uuid, get_id_usuario_sessao(), get_id_empresa_sessao(), commit=False)
            resposta = json_success(data=c.to_dict(), message="Evasão registrada; atendimentos em andamento cancelados.")
            return resposta, _meta_update(c, "status_consulta", dados.get("justificativa"))
        except BionException as ex:
            return json_error(ex.message, ex.status_code), {
                "id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}

    # ---- consentimento (bloqueante antes do 1º Atendimento)
    @staticmethod
    @bp_consulta.get("/<uuid>/consentimento")
    @requer_papel_clinico("enfermeiro","medico")
    def situacao_consentimento(uuid):
        try:
            return json_success(data=_svc.situacao_consentimento(uuid, get_id_empresa_sessao()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_consulta.post("/<uuid>/consentimento")
    @requer_papel_clinico("enfermeiro","medico")
    def registrar_consentimento(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.registrar_consentimento(uuid, dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=c.to_dict(), message="Consentimento registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_consulta.post("/<uuid>/consentimento/dispensar")
    @requer_papel_clinico("enfermeiro","medico")
    def dispensar_consentimento(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.dispensar_consentimento(uuid, dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=c.to_dict(), message="Consentimento dispensado por emergência.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)