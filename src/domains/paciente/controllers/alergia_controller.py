"""
Rotas JSON de alergias do paciente (parte do domínio clínico).

ALTERADO: toda rota passa id_empresa (sessão) pro service, e as rotas
de alergia/reação específica agora exigem uuid_paciente no path -- sem
isso não dá pra confirmar que a alergia pertence a um paciente da
empresa de quem está pedindo (ver AlergiaService).

ALTERADO: adicionar_reacao/remover_reacao passaram a usar
ReacaoAlergiaService, não AlergiaService -- responsabilidade de reação
isolada saiu de AlergiaService para não duplicar lógica entre os dois
services (ver ReacaoAlergiaService).

ALTERADO: rotas de escrita/exclusão passaram a registrar auditoria.
Critério usado (mesmo do domínio de usuário/paciente): alergia é dado
clínico usado em checagem de interação medicamentosa -- um erro ou uma
remoção indevida tem risco direto de segurança do paciente, então toda
escrita fica rastreável. Só `remover_alergia` recebeu `acao_sensivel`
(step-up + log atômico) -- é a única ação aqui que descarta o registro
"ativo" da alergia (soft delete) sem possibilidade de o próprio dado
continuar sendo consultado por engano; as demais (`adicionar_alergia`,
`atualizar_alergia`, `adicionar_reacao`, `restaurar_alergia`,
`remover_reacao`) usam `acesso_auditado` com a operação correspondente
-- registram log sem exigir reconfirmação de identidade, pra não gerar
fricção em fluxo clínico de uso frequente.

TODO antes de ativar `acao_sensivel` em remover_alergia: confirmar que
`AlergiaService.remover_alergia` NÃO chama `db.session.commit()`
internamente e passa a retornar `(resposta, detalhes)` com pelo menos
`id_registro`/`uuid_registro` (e `justificativa`, já que é
soft-delete) -- ver contrato descrito em `acaoSensivel.py`. Sem isso o
decorator falha silenciosamente ou quebra a atomicidade do log.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico, get_id_empresa_sessao
from src.domains.paciente.services import AlergiaService, ReacaoAlergiaService
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado

bp = Blueprint("alergia", __name__)
_svc = AlergiaService()
_svc_reacao = ReacaoAlergiaService()


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


    @staticmethod
    @bp.post("/<uuid_paciente>/alergias")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="adicionar alergia", operacao="escrita")
    def adicionar_alergia(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc.adicionar_alergia(uuid_paciente, dados, get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Alergia registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: atualiza codigo_substancia/flag_confirmado de uma alergia
    # já registrada. substancia não é editável (ver AlergiaAtualizarSchema).
    @staticmethod
    @bp.put("/<uuid_paciente>/alergias/<uuid_alergia>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="atualizar alergia", operacao="escrita")
    def atualizar_alergia(uuid_paciente, uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc.atualizar_alergia(uuid_paciente, uuid_alergia, dados, get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Alergia atualizada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Registra uma reação adicional numa alergia já existente
    @staticmethod
    @bp.post("/<uuid_paciente>/alergias/<uuid_alergia>/reacoes")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="adicionar reacao", operacao="escrita")
    def adicionar_reacao(uuid_paciente, uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc_reacao.adicionar_reacao(uuid_paciente, uuid_alergia, dados, get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Reação registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Remove a alergia inteira (soft delete -- histórico de reações
    # preservado fisicamente, ver AlergiaService.remover_alergia).
    # Motivo vem no corpo da requisição, mesmo padrão do domínio de
    # doença crônica.
    @staticmethod
    @bp.delete("/<uuid_paciente>/alergias/<uuid_alergia>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("remover_alergia", tabela="alergia")
    def remover_alergia(uuid_paciente, uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            _svc.remover_alergia(uuid_paciente, uuid_alergia, dados, get_id_empresa_sessao(), commit=False)
            return json_success(message="Alergia removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: reverte um soft delete de alergia.
    @staticmethod
    @bp.post("/<uuid_paciente>/alergias/<uuid_alergia>/restaurar")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="restaurar alergia", operacao="escrita")
    def restaurar_alergia(uuid_paciente, uuid_alergia):
        try:
            a = _svc.restaurar_alergia(uuid_paciente, uuid_alergia, get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Alergia restaurada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Remove apenas uma reação específica, mantendo a alergia e o
    # restante do histórico intactos
    @staticmethod
    @bp.delete("/<uuid_paciente>/alergias/reacoes/<uuid_reacao>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="remover reacao", operacao="exclusao-logica")
    def remover_reacao(uuid_paciente, uuid_reacao):
        try:
            _svc_reacao.remover_reacao(uuid_paciente, uuid_reacao, get_id_empresa_sessao())
            return json_success(message="Reação removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)