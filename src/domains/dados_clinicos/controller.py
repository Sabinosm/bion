"""Rotas JSON do registro de dados clínicos: sinais vitais, coleta clínica e input de protocolo.

Registrar o blueprint sob o MESMO prefixo do `bp_escrita` da alergia e do
`bp_binario` (o que expõe /<uuid_atendimento>/pacientes/<uuid_paciente>/...).

  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/sinais-vitais   (sem binário)
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/coleta-clinica  (exige binário completo)
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/coleta-clinica/<uuid_coleta>/input-protocolo
                                                                     (exige binário completo)

As rotas antigas (/<uuid_atendimento>/sinais-vitais, /<uuid_atendimento>/coleta-clinica
e /coleta-clinica/<uuid_coleta>/input-protocolo) deixam de existir: não passavam pelo guard.

Escrita: médico/enfermeiro; o resto (dono do atendimento, enfermeiro só em
triagem, em andamento, óbito) vem do guard no service.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao,
    get_funcao_clinica_sessao,
)
from src.domains.auditoria.acaoSensivel import acesso_auditado
from src.domains.atendimento.contexto_clinico_service import AutorClinico
from .service import DadosClinicosService

bp_dados_clinicos = Blueprint("dados_clinicos", __name__)
_svc_dados_clinicos = DadosClinicosService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>"


def _autor() -> AutorClinico:
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


class DadosClinicosController():

    @staticmethod
    @bp_dados_clinicos.post(_ESC + "/sinais-vitais")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="sinais vitais", operacao="escrita")
    def registrar_sinais_vitais(uuid_atendimento, uuid_paciente):
        """Registra um ou mais sinais vitais ({"sinais": [...]}) no Atendimento."""
        dados = request.get_json(silent=True) or {}
        try:
            registrados = _svc_dados_clinicos.registrar_sinais_vitais(
                uuid_atendimento, uuid_paciente, dados, _autor()
            )
            return json_success(
                data=[s.to_dict() for s in registrados],
                message="Sinais vitais registrados.", status=201,
            )
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_dados_clinicos.post(_ESC + "/coleta-clinica")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="coleta clinica", operacao="escrita")
    def registrar_coleta_clinica(uuid_atendimento, uuid_paciente):
        """Cria uma coleta clínica no Atendimento (exige binário completo)."""
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc_dados_clinicos.registrar_coleta_clinica(
                uuid_atendimento, uuid_paciente, dados, _autor()
            )
            return json_success(data=c.to_dict(), message="Coleta clínica registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_dados_clinicos.post(_ESC + "/coleta-clinica/<uuid_coleta>/input-protocolo")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="input protocolo", operacao="escrita")
    def registrar_input_protocolo(uuid_atendimento, uuid_paciente, uuid_coleta):
        """Registra o input de protocolo de uma coleta clínica do Atendimento (exige binário completo)."""
        dados = request.get_json(silent=True) or {}
        try:
            ip = _svc_dados_clinicos.registrar_input_protocolo(
                uuid_atendimento, uuid_paciente, uuid_coleta, dados, _autor()
            )
            return json_success(data=ip.to_dict(), message="Input de protocolo registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)