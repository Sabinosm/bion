"""alergia_controller.py

Rotas JSON das alergias do paciente: a leitura, em `bp` (/<uuid_paciente>/alergias),
e a escrita, em `bp_escrita`, aninhada no atendimento:

    /<uuid_atendimento>/pacientes/<uuid_paciente>/alergias[...]

`bp_escrita` deve ser registrado com o MESMO url_prefix do blueprint de atendimento.
A leitura é de médico ou enfermeiro da empresa. Quem pode escrever (dono do
atendimento, enfermeiro só em triagem, atendimento em andamento, paciente sem óbito)
é decidido pelo service (checagem comum de escrita clínica); o controller só monta o
AutorClinico a partir da sessão.

Remover alergia é ação sensível (step-up, justificativa e log de alteração na mesma
transação); as demais escritas não passam pelo log de alteração (autor e atendimento
já ficam gravados no registro). As rotas de ação sensível devolvem a meta NOOP nos
erros.
"""

from flask import Blueprint

from src.core.exceptions import BionException
from src.core.responses import json_success
from src.core.session import requer_papel_clinico, get_id_empresa_sessao
from src.domains.auditoria.acaoSensivel import acao_sensivel
from src.domains.paciente.services import AlergiaService, ReacaoAlergiaService
from .comum import autor_clinico, corpo_json, resposta_erro, resposta_erro_noop

bp = Blueprint("alergia", __name__)
bp_escrita = Blueprint("alergia_escrita", __name__)
_svc = AlergiaService()
_svc_reacao = ReacaoAlergiaService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/alergias"


class AlergiaController():

    # ------------------------------------------------------------ LEITURA
    @staticmethod
    @bp.get("/<uuid_paciente>/alergias")
    @requer_papel_clinico("medico", "enfermeiro")
    def listar_alergias(uuid_paciente):
        """Alergias não removidas do paciente."""
        try:
            itens = _svc.listar_alergias(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[a.to_dict() for a in itens])
        except BionException as ex:
            return resposta_erro(ex)

    # ------------------------------------------------------------ ESCRITA
    @staticmethod
    @bp_escrita.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    def adicionar_alergia(uuid_atendimento, uuid_paciente):
        """Cria a alergia (já com a primeira reação)."""
        try:
            a = _svc.adicionar_alergia(uuid_atendimento, uuid_paciente, corpo_json(), autor_clinico())
            return json_success(data=a.to_dict(), message="Alergia registrada.", status=201)
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp_escrita.put(_ESC + "/<uuid_alergia>")
    @requer_papel_clinico("medico", "enfermeiro")
    def atualizar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia):
        """Atualiza código da substância e confirmação (a substância não é editável)."""
        try:
            a = _svc.atualizar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia,
                                       corpo_json(), autor_clinico())
            return json_success(data=a.to_dict(), message="Alergia atualizada.")
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_alergia>/reacoes")
    @requer_papel_clinico("medico", "enfermeiro")
    def adicionar_reacao(uuid_atendimento, uuid_paciente, uuid_alergia):
        """Registra uma nova reação numa alergia existente."""
        try:
            a = _svc_reacao.adicionar_reacao(uuid_atendimento, uuid_paciente, uuid_alergia,
                                             corpo_json(), autor_clinico())
            return json_success(data=a.to_dict(), message="Reação registrada.", status=201)
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp_escrita.delete(_ESC + "/<uuid_alergia>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("remover_alergia", tabela="alergia")
    def remover_alergia(uuid_atendimento, uuid_paciente, uuid_alergia):
        """Soft delete com motivo (ação sensível: step-up e log atômico)."""
        dados = corpo_json()
        try:
            a = _svc.remover_alergia(uuid_atendimento, uuid_paciente, uuid_alergia, dados,
                                     autor_clinico(), commit=False)
            return json_success(message="Alergia removida."), {
                "id_registro": a.id,
                "uuid_registro": uuid_alergia,
                "operacao": "DELETE",
                "campo_alterado": "deletado",
                "valor_novo": "True",
                "justificativa": dados.get("observacoes_delete") or dados.get("motivo_delete"),
            }
        except BionException as ex:
            return resposta_erro_noop(ex)

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_alergia>/restaurar")
    @requer_papel_clinico("medico", "enfermeiro")
    def restaurar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia):
        """Reverte o soft delete."""
        try:
            a = _svc.restaurar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia, autor_clinico())
            return json_success(data=a.to_dict(), message="Alergia restaurada.")
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp_escrita.delete(_ESC + "/reacoes/<uuid_reacao>")
    @requer_papel_clinico("medico", "enfermeiro")
    def remover_reacao(uuid_atendimento, uuid_paciente, uuid_reacao):
        """Soft delete de uma reação registrada por engano."""
        try:
            _svc_reacao.remover_reacao(uuid_atendimento, uuid_paciente, uuid_reacao,
                                       corpo_json(), autor_clinico())
            return json_success(message="Reação removida.")
        except BionException as ex:
            return resposta_erro(ex)
