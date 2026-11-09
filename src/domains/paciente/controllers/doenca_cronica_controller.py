"""doenca_cronica_controller.py

Rotas JSON das doenças crônicas do paciente: a leitura, em `bp`
(/<uuid_paciente>/doencas-cronicas e /historico), e a escrita, em `bp_escrita`,
aninhada no atendimento:

    /<uuid_atendimento>/pacientes/<uuid_paciente>/doencas-cronicas[...]

`bp_escrita` deve ser registrado com o MESMO url_prefix do blueprint de atendimento.
A leitura é de médico ou enfermeiro da empresa (o histórico aparece pré-preenchido em
qualquer atendimento). Quem pode escrever é decidido pelo service (checagem comum de
escrita clínica); o controller só monta o AutorClinico a partir da sessão.

Remover doença é ação sensível (step-up, justificativa e log atômico, com meta NOOP nos
erros); as demais escritas não passam pelo log de alteração (autor e atendimento já
ficam na tabela). Mudança de status, CID ou início NÃO é PUT: é POST .../<uuid>/revisar,
que fecha a linha vigente e cria uma nova. O PUT só corrige `observacoes`.
"""

from flask import Blueprint

from src.core.exceptions import BionException
from src.core.responses import json_success
from src.core.session import requer_papel_clinico, get_id_empresa_sessao
from src.domains.auditoria.acaoSensivel import acao_sensivel
from src.domains.paciente.services import DoencaCronicaService
from .comum import autor_clinico, corpo_json, resposta_erro, resposta_erro_noop

bp = Blueprint("doencas-cronicas", __name__)
# Nome próprio: dois blueprints com o mesmo name no mesmo app dão erro no Flask.
bp_escrita = Blueprint("doenca_cronica_escrita", __name__)
_svc = DoencaCronicaService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/doencas-cronicas"


class DoencaCronicaController():

    # ------------------------------------------------------------ LEITURA
    @staticmethod
    @bp.get("/<uuid_paciente>/doencas-cronicas")
    @requer_papel_clinico("medico", "enfermeiro")
    def listar_doencas(uuid_paciente):
        """Doenças vigentes do paciente."""
        try:
            itens = _svc.listar_doencas(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[d.to_dict() for d in itens])
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp.get("/<uuid_paciente>/doencas-cronicas/historico")
    @requer_papel_clinico("medico", "enfermeiro")
    def listar_historico(uuid_paciente):
        """Vigentes e encerradas por revisão (linha do tempo), sem removidas."""
        try:
            itens = _svc.listar_historico(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[d.to_dict() for d in itens])
        except BionException as ex:
            return resposta_erro(ex)

    # ------------------------------------------------------------ ESCRITA
    @staticmethod
    @bp_escrita.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    def adicionar_doenca(uuid_atendimento, uuid_paciente):
        """Registra uma doença crônica vigente."""
        try:
            d = _svc.adicionar_doenca(uuid_atendimento, uuid_paciente, corpo_json(), autor_clinico())
            return json_success(data=d.to_dict(), message="Doença crônica registrada.", status=201)
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp_escrita.put(_ESC + "/<uuid_doenca>")
    @requer_papel_clinico("medico", "enfermeiro")
    def atualizar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        """Só `observacoes`. Status, CID e início: use /revisar."""
        try:
            d = _svc.atualizar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca,
                                      corpo_json(), autor_clinico())
            return json_success(data=d.to_dict(), message="Doença crônica atualizada.")
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_doenca>/revisar")
    @requer_papel_clinico("medico", "enfermeiro")
    def revisar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        """Fecha a linha vigente e cria a nova; devolve a NOVA (201)."""
        try:
            d = _svc.revisar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca,
                                    corpo_json(), autor_clinico())
            return json_success(data=d.to_dict(), message="Doença crônica revisada.", status=201)
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp_escrita.delete(_ESC + "/<uuid_doenca>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("remover_doenca_cronica", tabela="doenca_cronica")
    def remover_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        """Soft delete com motivo (ação sensível: step-up e log atômico)."""
        dados = corpo_json()
        try:
            d = _svc.remover_doenca(uuid_atendimento, uuid_paciente, uuid_doenca, dados,
                                    autor_clinico(), commit=False)
            return json_success(message="Doença crônica removida."), {
                "id_registro": d.id,
                "uuid_registro": uuid_doenca,
                "operacao": "DELETE",
                "campo_alterado": "deletado",
                "valor_novo": "True",
                "justificativa": dados.get("observacoes_delete") or dados.get("motivo_delete"),
            }
        except BionException as ex:
            return resposta_erro_noop(ex)

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_doenca>/restaurar")
    @requer_papel_clinico("medico", "enfermeiro")
    def restaurar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        """Reverte o soft delete."""
        try:
            d = _svc.restaurar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca, autor_clinico())
            return json_success(data=d.to_dict(), message="Doença crônica restaurada.")
        except BionException as ex:
            return resposta_erro(ex)
