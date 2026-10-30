"""controller.py

Rotas JSON do registro de dados clínicos dentro de um Atendimento: sinais
vitais, coleta clínica e input de protocolo, mais a execução determinística de
um protocolo sobre o input vigente e as duas leituras que alimentam o
formulário (protocolos disponíveis e estrutura de campos de um protocolo).

Registrar o blueprint sob o MESMO prefixo do `bp_escrita` da alergia e do
`bp_binario` (o que expõe /<uuid_atendimento>/pacientes/<uuid_paciente>/...).

  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/sinais-vitais   (sem binário)
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/coleta-clinica  (exige binário completo)
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/coleta-clinica/<uuid_coleta>/input-protocolo
                                                                     (exige binário completo)
  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/protocolos/<uuid_protocolo>/executar
  GET  /<uuid_atendimento>/pacientes/<uuid_paciente>/protocolos-disponiveis
  GET  /<uuid_atendimento>/pacientes/<uuid_paciente>/protocolos/<uuid_protocolo>/estrutura

As rotas antigas (/<uuid_atendimento>/sinais-vitais, /<uuid_atendimento>/coleta-clinica
e /coleta-clinica/<uuid_coleta>/input-protocolo) deixam de existir: não passavam pelo guard.

Escrita: médico/enfermeiro; o resto (dono do atendimento, enfermeiro só em
triagem, em andamento, óbito) vem do guard no service. As leituras de protocolo
também são de médico/enfermeiro. Toda rota é auditada; no erro devolve a meta
NOOP, porque o decorator de auditoria não olha o status HTTP e, sem ela,
registraria o erro como acesso com sucesso.
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
from .execucao_atendimento_service import ExecucaoAtendimentoService

bp_dados_clinicos = Blueprint("dados_clinicos", __name__)
_svc_dados_clinicos = DadosClinicosService()
_svc_execucao = ExecucaoAtendimentoService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>"


def _autor() -> AutorClinico:
    """Monta o AutorClinico a partir da sessão (nunca do corpo da requisição)."""
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


def _corpo_json() -> dict:
    """Corpo JSON da requisição; vazio se ausente. O service rejeita o que não for objeto."""
    return request.get_json(silent=True) or {}


def _erro(ex: BionException):
    """Resposta de erro com meta NOOP (ver o docstring do módulo)."""
    return json_error(ex.message, ex.status_code, erros=ex.erros), {"operacao": "NOOP"}


class DadosClinicosController():

    @staticmethod
    @bp_dados_clinicos.post(_ESC + "/sinais-vitais")
    @requer_papel_clinico("medico", "enfermeiro")
    def registrar_sinais_vitais(uuid_atendimento, uuid_paciente):
        """Registra um ou mais sinais vitais ({"sinais": [...]}) no Atendimento."""
        try:
            registrados = _svc_dados_clinicos.registrar_sinais_vitais(
                uuid_atendimento, uuid_paciente, _corpo_json(), _autor()
            )
            return json_success(
                data=[s.to_dict() for s in registrados],
                message="Sinais vitais registrados.", status=201,
            )
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_dados_clinicos.post(_ESC + "/coleta-clinica")
    @requer_papel_clinico("medico", "enfermeiro")
    def registrar_coleta_clinica(uuid_atendimento, uuid_paciente):
        """Cria uma coleta clínica no Atendimento (exige binário completo)."""
        try:
            c = _svc_dados_clinicos.registrar_coleta_clinica(
                uuid_atendimento, uuid_paciente, _corpo_json(), _autor()
            )
            return json_success(data=c.to_dict(), message="Coleta clínica registrada.", status=201)
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_dados_clinicos.post(_ESC + "/coleta-clinica/<uuid_coleta>/input-protocolo")
    @requer_papel_clinico("medico", "enfermeiro")
    def registrar_input_protocolo(uuid_atendimento, uuid_paciente, uuid_coleta):
        """Registra o input de protocolo de uma coleta clínica do Atendimento (exige binário completo)."""
        try:
            ip = _svc_dados_clinicos.registrar_input_protocolo(
                uuid_atendimento, uuid_paciente, uuid_coleta, _corpo_json(), _autor()
            )
            return json_success(data=ip.to_dict(), message="Input de protocolo registrado.", status=201)
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_dados_clinicos.post(_ESC + "/protocolos/<uuid_protocolo>/executar")
    @requer_papel_clinico("medico", "enfermeiro")
    def executar_protocolo(uuid_atendimento, uuid_paciente, uuid_protocolo):
        """Executa o protocolo sobre o input vigente do atendimento (determinístico).
        Idempotente: se o protocolo já foi executado neste input, devolve a execução
        existente com 200 (e não 409); a execução nova responde 201."""
        try:
            e, criada = _svc_execucao.executar(uuid_atendimento, uuid_paciente, uuid_protocolo, _autor())
            if criada:
                return json_success(data=e.to_dict(), message="Protocolo executado.", status=201)
            return json_success(
                data=e.to_dict(),
                message="Protocolo já executado neste input; resultado existente.",
                status=200,
            )
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_dados_clinicos.get(_ESC + "/protocolos-disponiveis")
    @requer_papel_clinico("medico", "enfermeiro")
    def protocolos_disponiveis(uuid_atendimento, uuid_paciente):
        """Catálogo ativo, de escopo compatível com o tipo de atendimento e liberado pela empresa,
        já com favorito / default_pessoal / padrao_institucional / politica (favoritos primeiro)."""
        try:
            lista = _svc_execucao.listar_disponiveis(uuid_atendimento, _autor(), get_id_empresa_sessao())
            return json_success(data=lista)  # o service já devolve dicts
        except BionException as ex:
            return _erro(ex)

    @staticmethod
    @bp_dados_clinicos.get(_ESC + "/protocolos/<uuid_protocolo>/estrutura")
    @requer_papel_clinico("medico", "enfermeiro")
    def estrutura_protocolo(uuid_atendimento, uuid_paciente, uuid_protocolo):
        """Campos esperados do protocolo (para o front montar o formulário do input)."""
        try:
            return json_success(data=_svc_execucao.estrutura_utilizavel(
                uuid_atendimento, uuid_protocolo, _autor()))
        except BionException as ex:
            return _erro(ex)
