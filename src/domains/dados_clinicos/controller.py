"""Rotas JSON do registro de dados clínicos: sinais vitais, coleta clínica e input de protocolo.

ALTERADO (Bloco 2): sinais vitais e coleta clínica viram rotas aninhadas no
Atendimento E no Paciente (o guard confere que o atendimento é daquele
paciente). Registrar este blueprint sob o MESMO prefixo do `bp_escrita` da
alergia (/atendimentos).

  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/sinais-vitais    corpo: {"sinais": [...]}
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/coleta-clinica   (exige binário completo)
  POST /coleta-clinica/<uuid_coleta>/input-protocolo                  (SEM ALTERAÇÃO, próximo passo)

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
        """Registra um ou mais sinais vitais (tudo ou nada). Livre do binário."""
        dados = request.get_json(silent=True) or {}
        try:
            registrados = _svc_dados_clinicos.registrar_sinais_vitais(
                uuid_atendimento, uuid_paciente,
                dados.get("sinais") if isinstance(dados, dict) else None,
                _autor(),
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
        """Cria uma coleta clínica no Atendimento. Exige o binário completo."""
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc_dados_clinicos.registrar_coleta_clinica(
                uuid_atendimento, uuid_paciente, dados, _autor()
            )
            return json_success(data=c.to_dict(), message="Coleta clínica registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_dados_clinicos.post("/coleta-clinica/<uuid_coleta>/input-protocolo")
    @requer_papel_clinico("medico", "enfermeiro")
    def registrar_input_protocolo(uuid_coleta):
        """Registra o input de protocolo (queixa, sinais, fluxograma) de uma coleta clínica.
        SEM ALTERAÇÃO (próximo passo): ainda sem guard e sem gate."""
        dados = request.get_json(silent=True) or {}
        try:
            ip = _svc_dados_clinicos.registrar_input_protocolo(uuid_coleta, dados)
            return json_success(data=ip.to_dict(), message="Input de protocolo registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)