"""
Rotas JSON de doenças crônicas do paciente.

BLOCO 2: a LEITURA continua em `bp` (/<uuid_paciente>/doencas-cronicas e
/historico, só login + tenant: o histórico aparece pré-preenchido em
qualquer atendimento). A ESCRITA vai para `bp_escrita`, aninhada no
atendimento:

    /<uuid_atendimento>/pacientes/<uuid_paciente>/doencas-cronicas[...]

`bp_escrita` deve ser registrado com o MESMO url_prefix de bp_atendimento.
Quem pode escrever (dono do atendimento, enfermeiro só em triagem,
atendimento em andamento, paciente sem óbito) é decidido pelo service
(ContextoClinicoService); o controller só monta o AutorClinico a partir da
sessão. `remover_doenca` é `acao_sensivel` (contrato (resposta, detalhes)
com justificativa); as demais escritas não passam pelo log (autor e atendimento já ficam na tabela).

Mudança de status/CID/desde NÃO é PUT: é POST .../<uuid>/revisar, que fecha
a linha vigente e cria uma nova. O PUT só corrige `observacoes`.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_login, requer_papel_clinico, get_id_empresa_sessao,
    get_id_usuario_sessao, get_funcao_clinica_sessao,
)
from src.domains.auditoria.acaoSensivel import acao_sensivel
from src.domains.paciente.services import DoencaCronicaService
from src.domains.atendimento.contexto_clinico_service import AutorClinico

bp = Blueprint("doencas-cronicas", __name__)
# Nome próprio: dois blueprints com o mesmo name no mesmo app dão erro no Flask.
# Se você já registra os de escrita com name=..., pode voltar a "atendimento".
bp_escrita = Blueprint("doenca_cronica_escrita", __name__)
_svc = DoencaCronicaService()


def _autor() -> AutorClinico:
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/doencas-cronicas"


class DoencaCronicaController():

    # ------------------------------------------------------------ LEITURA
    @staticmethod
    @bp.get("/<uuid_paciente>/doencas-cronicas")
    @requer_login
    def listar_doencas(uuid_paciente):
        try:
            itens = _svc.listar_doencas(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[d.to_dict() for d in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/<uuid_paciente>/doencas-cronicas/historico")
    @requer_login
    def listar_historico(uuid_paciente):
        try:
            itens = _svc.listar_historico(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[d.to_dict() for d in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # ------------------------------------------------------------ ESCRITA
    @staticmethod
    @bp_escrita.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    def adicionar_doenca(uuid_atendimento, uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.adicionar_doenca(uuid_atendimento, uuid_paciente, dados, _autor())
            return json_success(data=d.to_dict(), message="Doença crônica registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_escrita.put(_ESC + "/<uuid_doenca>")
    @requer_papel_clinico("medico", "enfermeiro")
    def atualizar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        """Só `observacoes`. Status/CID/desde: use /revisar."""
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.atualizar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca, dados, _autor())
            return json_success(data=d.to_dict(), message="Doença crônica atualizada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_doenca>/revisar")
    @requer_papel_clinico("medico", "enfermeiro")
    def revisar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        """Fecha a linha vigente e cria a nova; devolve a NOVA (201)."""
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.revisar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca, dados, _autor())
            return json_success(data=d.to_dict(), message="Doença crônica revisada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_escrita.delete(_ESC + "/<uuid_doenca>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("remover_doenca_cronica", tabela="doenca_cronica")
    def remover_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.remover_doenca(uuid_atendimento, uuid_paciente, uuid_doenca, dados,
                                    _autor(), commit=False)
            resposta = json_success(message="Doença crônica removida.")
            return resposta, {
                "id_registro": d.id,
                "uuid_registro": uuid_doenca,
                "operacao": "DELETE",
                "campo_alterado": "deletado",
                "valor_novo": "True",
                "justificativa": dados.get("observacoes_delete") or dados.get("motivo_delete"),
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid_doenca, "operacao": "NOOP"}

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_doenca>/restaurar")
    @requer_papel_clinico("medico", "enfermeiro")
    def restaurar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca):
        try:
            d = _svc.restaurar_doenca(uuid_atendimento, uuid_paciente, uuid_doenca, _autor())
            return json_success(data=d.to_dict(), message="Doença crônica restaurada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)