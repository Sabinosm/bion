"""
Rotas JSON de alergias do paciente.

BLOCO 2: a LEITURA continua em `bp` (/<uuid_paciente>/alergias, só login +
tenant: o histórico aparece pré-preenchido em qualquer atendimento). A
ESCRITA mudou para `bp_escrita`, aninhada no atendimento:

    /<uuid_atendimento>/pacientes/<uuid_paciente>/alergias[...]

`bp_escrita` deve ser registrado com o MESMO url_prefix de bp_atendimento.
Quem pode escrever (dono do atendimento, enfermeiro só em triagem,
atendimento em andamento, paciente sem óbito) é decidido pelo service
(ContextoClinicoService); o controller só monta o AutorClinico a partir da
sessão. `remover_alergia` segue como `acao_sensivel` (contrato
(resposta, detalhes) com justificativa); as demais escritas usam
`acesso_auditado`. Reação removida: soft delete com motivo no corpo.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_login, requer_papel_clinico, get_id_empresa_sessao,
    get_id_usuario_sessao, get_funcao_clinica_sessao,
)
from src.domains.paciente.services import AlergiaService, ReacaoAlergiaService
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado
from src.domains.atendimento.contexto_clinico_service import AutorClinico

bp = Blueprint("alergia", __name__)
bp_escrita = Blueprint("atendimento", __name__)
_svc = AlergiaService()
_svc_reacao = ReacaoAlergiaService()


def _autor() -> AutorClinico:
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/alergias"


class AlergiaController():

    @staticmethod
    @bp.get("/<uuid_paciente>/alergias")
    @requer_login
    def listar_alergias(uuid_paciente):
        try:
            itens = _svc.listar_alergias(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[a.to_dict() for a in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # ------------------------------------------------------------ ESCRITA
    @staticmethod
    @bp_escrita.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="adicionar alergia", operacao="escrita")
    def adicionar_alergia(uuid_atendimento, uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc.adicionar_alergia(uuid_atendimento, uuid_paciente, dados, _autor())
            return json_success(data=a.to_dict(), message="Alergia registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_escrita.put(_ESC + "/<uuid_alergia>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="atualizar alergia", operacao="escrita")
    def atualizar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc.atualizar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia, dados, _autor())
            return json_success(data=a.to_dict(), message="Alergia atualizada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_alergia>/reacoes")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="adicionar reacao", operacao="escrita")
    def adicionar_reacao(uuid_atendimento, uuid_paciente, uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc_reacao.adicionar_reacao(uuid_atendimento, uuid_paciente, uuid_alergia, dados, _autor())
            return json_success(data=a.to_dict(), message="Reação registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_escrita.delete(_ESC + "/<uuid_alergia>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("remover_alergia", tabela="alergia")
    def remover_alergia(uuid_atendimento, uuid_paciente, uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc.remover_alergia(uuid_atendimento, uuid_paciente, uuid_alergia, dados,
                                     _autor(), commit=False)
            resposta = json_success(message="Alergia removida.")
            return resposta, {
                "id_registro": a.id,
                "uuid_registro": uuid_alergia,
                "operacao": "DELETE",
                "campo_alterado": "deletado",
                "valor_novo": "True",
                "justificativa": dados.get("observacoes_delete") or dados.get("motivo_delete"),
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid_alergia, "operacao": "NOOP"}

    @staticmethod
    @bp_escrita.post(_ESC + "/<uuid_alergia>/restaurar")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="restaurar alergia", operacao="escrita")
    def restaurar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia):
        try:
            a = _svc.restaurar_alergia(uuid_atendimento, uuid_paciente, uuid_alergia, _autor())
            return json_success(data=a.to_dict(), message="Alergia restaurada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_escrita.delete(_ESC + "/reacoes/<uuid_reacao>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="remover reacao", operacao="exclusao-logica")
    def remover_reacao(uuid_atendimento, uuid_paciente, uuid_reacao):
        dados = request.get_json(silent=True) or {}
        try:
            _svc_reacao.remover_reacao(uuid_atendimento, uuid_paciente, uuid_reacao, dados, _autor())
            return json_success(message="Reação removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)