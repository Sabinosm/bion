"""controller.py

Rotas JSON do ciclo de vida do Atendimento: listagem, detalhe, linha do tempo
da Consulta, abertura (triagem, avaliação médica e reavaliação), finalização e
cancelamento.

As permissões seguem o nível mínimo do papel clínico (médico inclui enfermeiro):
triagem para enfermeiro ou médico, avaliação médica e reavaliação só para
médico. Finalizar e cancelar são do profissional que abriu o atendimento (o
service responde 403 para os demais). Toda rota passa a empresa da sessão ao
service, porque o Atendimento herda a posse da Consulta e o UUID sozinho não
prova posse.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico, get_funcao_clinica_sessao, get_id_usuario_sessao, get_id_empresa_sessao,
)
from src.domains.auditoria.acaoSensivel import acesso_auditado
from .service import AtendimentoService
from .detalhe_atendimento_service import DetalheAtendimentoService  # provisório: ver o arquivo

bp_atendimento = Blueprint("atendimento", __name__)
_svc = AtendimentoService()
_detalhe = DetalheAtendimentoService()


def _corpo_json() -> dict:
    """Corpo JSON da requisição; vazio se ausente ou se não for um objeto."""
    dados = request.get_json(silent=True)
    return dados if isinstance(dados, dict) else {}


class AtendimentoController():

    @staticmethod
    @bp_atendimento.get("/")
    @requer_papel_clinico("enfermeiro", "medico")
    def lista_atendimentos():
        """Lista os Atendimentos da empresa do usuário logado."""
        itens = _svc.listar(get_id_empresa_sessao())
        return json_success(data=[a.to_dict() for a in itens])

    @staticmethod
    @bp_atendimento.get("/<uuid>")
    @requer_papel_clinico("enfermeiro", "medico")
    def detalhe_atendimento(uuid):
        """Atendimento pelo UUID, com o paciente e a continuidade (pode_continuar)."""
        try:
            dados = _svc.buscar_resumo(uuid, get_id_empresa_sessao(), get_id_usuario_sessao())
            return json_success(data=dados)
        except BionException as ex:
            # @acesso_auditado não olha o status HTTP: NOOP evita logar o erro como leitura com sucesso
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp_atendimento.get("/<uuid>/detalhe")
    @requer_papel_clinico("enfermeiro", "medico")
    @acesso_auditado(recurso="detalhe completo do atendimento", operacao="leitura")
    def detalhe_completo(uuid):
        """Resumo completo de como foi (ou é) o atendimento, em JSON pronto para exibir.

        Mesma fonte do PDF detalhado (ver detalhe_atendimento_service.py), sem CPF e sem
        nascimento do paciente. Leitura auditada com uuid_paciente; no erro devolve NOOP.
        """
        try:
            dados, uuid_paciente = _detalhe.obter(uuid, get_id_empresa_sessao(), get_id_usuario_sessao())
            return json_success(data=dados), {"uuid_paciente": uuid_paciente}
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros), {"operacao": "NOOP"}

    @staticmethod
    @bp_atendimento.get("/consulta/<uuid_consulta>")
    @requer_papel_clinico("enfermeiro", "medico")
    def atendimentos_da_consulta(uuid_consulta):
        """Linha do tempo da Consulta: os Atendimentos em ordem cronológica, cada um com
        `profissional` ({uuid, nome_completo, funcao_clinica})."""
        try:
            itens, uuid_paciente = _svc.listar_resumo_por_consulta(uuid_consulta, get_id_empresa_sessao())
            return json_success(data=itens)
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp_atendimento.post("/consulta/<uuid_consulta>/abrir-triagem")
    @requer_papel_clinico("enfermeiro", "medico")
    def abrir_triagem(uuid_consulta):
        """Abre um Atendimento do tipo triagem para a Consulta informada.
        409 se o consentimento LGPD estiver pendente, a Consulta encerrada ou já houver
        um atendimento em andamento."""
        try:
            a = _svc.abrir_triagem(uuid_consulta, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Triagem aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp_atendimento.post("/consulta/<uuid_consulta>/abrir-avaliacao-medica")
    @requer_papel_clinico("medico")
    def abrir_avaliacao_medica(uuid_consulta):
        """Abre um Atendimento do tipo avaliação médica para a Consulta informada."""
        try:
            a = _svc.abrir_avaliacao_medica(uuid_consulta, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Avaliação médica aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp_atendimento.post("/consulta/<uuid_consulta>/abrir-reavaliacao")
    @requer_papel_clinico("medico")
    def abrir_reavaliacao(uuid_consulta):
        """Abre um Atendimento do tipo reavaliação (retorno do médico) para a Consulta informada.
        409 se a Consulta não estiver em em-observacao, houver atendimento em andamento,
        o consentimento estiver pendente ou a Consulta estiver encerrada."""
        try:
            a = _svc.abrir_reavaliacao(uuid_consulta, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Reavaliação aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp_atendimento.post("/<uuid_atendimento>/finalizar")
    @requer_papel_clinico("enfermeiro", "medico")
    def finalizar_atendimento(uuid_atendimento):
        """Finaliza um Atendimento em andamento. Corpo opcional: {"observacoes": "..."}.
        Só o dono (403); exige binário completo e sem pendência clínica (409).
        Avaliação médica e reavaliação: só médico (403 para enfermeiro)."""
        dados = _corpo_json()
        try:
            a = _svc.finalizar(
                uuid_atendimento, get_id_empresa_sessao(), get_id_usuario_sessao(),
                dados.get("observacoes"),
                eh_medico=get_funcao_clinica_sessao() == "medico",
            )
            return json_success(data=a.to_dict(), message="Atendimento finalizado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp_atendimento.post("/<uuid_atendimento>/cancelar")
    @requer_papel_clinico("enfermeiro", "medico")
    def cancelar_atendimento(uuid_atendimento):
        """Cancela um Atendimento em andamento. Só o dono; não exige binário.
        Corpo opcional: {"motivo_cancelamento": "erro-abertura"}."""
        dados = _corpo_json()
        try:
            a = _svc.cancelar(
                uuid_atendimento, get_id_empresa_sessao(), get_id_usuario_sessao(),
                dados.get("motivo_cancelamento"),
            )
            return json_success(data=a.to_dict(), message="Atendimento cancelado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)
