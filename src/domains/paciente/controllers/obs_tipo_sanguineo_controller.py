from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_login, requer_papel_clinico, get_id_empresa_sessao,
    get_id_usuario_sessao, get_funcao_clinica_sessao,
)
from src.domains.paciente.services import ObservacaoTipoSanguineoService
from src.domains.auditoria.acaoSensivel import acesso_auditado
from src.domains.atendimento.contexto_clinico_service import AutorClinico

bp = Blueprint("tipo_sanguineo", __name__)
bp_escrita = Blueprint("tipo_sanguineo_escrita", __name__)
_svc = ObservacaoTipoSanguineoService()


def _autor() -> AutorClinico:
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/tipo-sanguineo"


class ObservacaoTipoSanguineoController():

    # ------------------------------------------------------------ LEITURA
    @staticmethod
    @bp.get("/<uuid_paciente>/tipo-sanguineo")
    @requer_login
    def tipo_vigente(uuid_paciente):
        """Tipo vigente; data=null se nunca foi registrado."""
        try:
            obs = _svc.tipo_vigente(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=obs.to_dict() if obs else None)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/<uuid_paciente>/tipo-sanguineo/historico")
    @requer_login
    def historico_tipo_sanguineo(uuid_paciente):
        try:
            itens = _svc.historico(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[o.to_dict() for o in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # ------------------------------------------------------------ ESCRITA
    @staticmethod
    @bp_escrita.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="registrar tipo sanguineo", operacao="escrita")
    def registrar_tipo_sanguineo(uuid_atendimento, uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            o = _svc.registrar_tipo_sanguineo(uuid_atendimento, uuid_paciente, dados, _autor())
            return json_success(data=o.to_dict(), message="Tipo sanguíneo registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)