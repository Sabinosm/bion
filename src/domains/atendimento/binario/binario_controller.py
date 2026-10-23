"""Rotas JSON do binário (conferência das 4 seções) dentro de um Atendimento.

Registrar o blueprint `bp_binario` sob o MESMO prefixo do `bp_escrita` da
alergia (o que expõe /<uuid_atendimento>/pacientes/<uuid_paciente>/...).

  GET  /<uuid_atendimento>/binario                              estado + pré-preenchimento
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/binario            agregada (4 seções)
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/binario/<secao>    granular

Leitura: só login + tenant. Escrita: médico/enfermeiro; o resto (dono do
atendimento, enfermeiro só em triagem, em andamento, óbito) vem do guard.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_login, requer_papel_clinico, get_id_empresa_sessao,
    get_id_usuario_sessao, get_funcao_clinica_sessao,
)
from src.domains.auditoria.acaoSensivel import acesso_auditado
from src.domains.atendimento.contexto_clinico_service import AutorClinico
from .binario_service import BinarioService

bp_binario = Blueprint("binario", __name__)
_svc = BinarioService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/binario"


def _autor() -> AutorClinico:
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


class BinarioController():

    @staticmethod
    @bp_binario.get("/<uuid_atendimento>/binario")
    @requer_login
    @acesso_auditado(recurso="estado do binario", operacao="leitura")
    def estado_binario(uuid_atendimento):
        try:
            return json_success(data=_svc.estado(uuid_atendimento, get_id_empresa_sessao()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_binario.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="conferir binario", operacao="escrita")
    def conferir_binario(uuid_atendimento, uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            r = _svc.conferir_binario(uuid_atendimento, uuid_paciente, dados, _autor())
            return json_success(data=r, message="Binário conferido.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_binario.post(_ESC + "/<secao>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="conferir secao do binario", operacao="escrita")
    def conferir_secao(uuid_atendimento, uuid_paciente, secao):
        dados = request.get_json(silent=True) or {}
        try:
            r = _svc.conferir_secao(secao, uuid_atendimento, uuid_paciente, dados, _autor())
            return json_success(data=r, message="Seção do binário conferida.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
        
    @staticmethod
    @bp_binario.get("/<uuid_atendimento>/binario/do-paciente")
    @requer_login
    @acesso_auditado(recurso="binario do paciente", operacao="leitura")
    def binario_do_paciente(uuid_atendimento):
        try:
            return json_success(
                data=_svc.binario_do_paciente(uuid_atendimento, get_id_empresa_sessao()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)