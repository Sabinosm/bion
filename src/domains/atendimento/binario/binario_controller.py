"""binario_controller.py

Rotas JSON do binário: a conferência das quatro seções clínicas (alergias,
medicamentos, tipo sanguíneo e doença crônica) dentro de um Atendimento. As
rotas de leitura mostram o estado da conferência e o binário montado a partir
dos registros ativos do paciente; as de escrita conferem todas as seções de uma
vez (agregada) ou uma seção por vez (granular).

Registrar o blueprint sob o MESMO prefixo das rotas de escrita de alergia e de
conduta de enfermagem, o que expõe /<uuid_atendimento>/pacientes/<uuid_paciente>/...
Leitura e escrita são de médico ou enfermeiro da empresa; na escrita, o restante
(dono do atendimento, enfermeiro só em triagem, em andamento, paciente sem
óbito) vem da checagem comum de escrita clínica no service.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao, get_funcao_clinica_sessao,
)
from src.domains.auditoria.acaoSensivel import acesso_auditado
from src.domains.atendimento.contexto_clinico_service import AutorClinico
from .binario_service import BinarioService

bp_binario = Blueprint("binario", __name__)
_svc = BinarioService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/binario"


def _erro(ex: BionException):
    """Resposta de erro com meta NOOP: o decorator de auditoria não olha o status HTTP e,
    sem o NOOP, registraria o erro como acesso com sucesso."""
    return json_error(ex.message, ex.status_code, erros=ex.erros), {"operacao": "NOOP"}


def _autor() -> AutorClinico:
    """Monta o AutorClinico a partir da sessão (nunca do corpo da requisição)."""
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


class BinarioController():

    @staticmethod
    @bp_binario.get("/<uuid_atendimento>/binario")
    @requer_papel_clinico("enfermeiro", "medico")
    @acesso_auditado(recurso="estado do binario", operacao="leitura")
    def estado_binario(uuid_atendimento):
        """Estado de conferência de cada seção, com os registros ativos do paciente como
        pré-preenchimento nas seções pendentes."""
        try:
            return json_success(data=_svc.estado(uuid_atendimento, get_id_empresa_sessao()))
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_binario.get("/<uuid_atendimento>/binario/do-paciente")
    @requer_papel_clinico("enfermeiro", "medico")
    @acesso_auditado(recurso="binario do paciente", operacao="leitura")
    def binario_do_paciente(uuid_atendimento):
        """Binário no formato do corpo da rota agregada, montado dos registros ativos do paciente
        e da última conferência confirmada. Só leitura: não grava nada."""
        try:
            return json_success(
                data=_svc.binario_do_paciente(uuid_atendimento, get_id_empresa_sessao()))
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_binario.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="conferir binario", operacao="escrita")
    def conferir_binario(uuid_atendimento, uuid_paciente):
        """Confere as quatro seções de uma vez, atomicamente (corpo: BinarioIn)."""
        dados = request.get_json(silent=True) or {}
        try:
            r = _svc.conferir_binario(uuid_atendimento, uuid_paciente, dados, _autor())
            return json_success(data=r, message="Binário conferido.", status=201)
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_binario.post(_ESC + "/<secao>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="conferir secao do binario", operacao="escrita")
    def conferir_secao(uuid_atendimento, uuid_paciente, secao):
        """Confere uma única seção (alergias, medicamentos, tipo_sanguineo ou doenca_cronica)."""
        dados = request.get_json(silent=True) or {}
        try:
            r = _svc.conferir_secao(secao, uuid_atendimento, uuid_paciente, dados, _autor())
            return json_success(data=r, message="Seção do binário conferida.", status=201)
        except BionException as ex:
            return _erro(ex)
