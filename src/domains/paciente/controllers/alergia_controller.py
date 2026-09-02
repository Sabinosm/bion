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
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_empresa_sessao
from src.domains.paciente.services import AlergiaService, ReacaoAlergiaService

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
    @requer_papel("medico", "enfermeiro")
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
    @requer_papel("medico", "enfermeiro")
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
    @requer_papel("medico", "enfermeiro")
    def adicionar_reacao(uuid_paciente, uuid_alergia):
        dados = request.get_json(silent=True) or {}
        try:
            a = _svc_reacao.adicionar_reacao(uuid_paciente, uuid_alergia, dados, get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Reação registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Remove a alergia inteira (com todo o histórico de reações)
    @staticmethod
    @bp.delete("/<uuid_paciente>/alergias/<uuid_alergia>")
    @requer_papel("medico", "enfermeiro")
    def remover_alergia(uuid_paciente, uuid_alergia):
        try:
            _svc.remover_alergia(uuid_paciente, uuid_alergia, get_id_empresa_sessao())
            return json_success(message="Alergia removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Remove apenas uma reação específica, mantendo a alergia e o
    # restante do histórico intactos
    @staticmethod
    @bp.delete("/<uuid_paciente>/alergias/reacoes/<uuid_reacao>")
    @requer_papel("medico", "enfermeiro")
    def remover_reacao(uuid_paciente, uuid_reacao):
        try:
            _svc_reacao.remover_reacao(uuid_paciente, uuid_reacao, get_id_empresa_sessao())
            return json_success(message="Reação removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)