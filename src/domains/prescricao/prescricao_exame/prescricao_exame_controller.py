"""Rotas JSON da entidade PrescricaoExame: exames prescritos.

Sem step-up; auditoria por @acesso_auditado (ver ../auditoria_helpers.py)."""

from flask import Blueprint, request
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao
from src.domains.auditoria.acaoSensivel import acesso_auditado
from .prescricao_exame_service import PrescricaoExameService
from src.domains.auditoria.auditoria_helpers_service import detalhes, erro
from ..schema_prescricoes import ExamePrescritoIn, ExamePrescritoPatch, formatar_erros_pydantic

bp_prescricao_exame = Blueprint("prescricao_exame", __name__)
_svc_prescricao_exame = PrescricaoExameService()

class PrescricaoExameController():

    @staticmethod
    @bp_prescricao_exame.post("/<uuid_resultado>/exames")
    @requer_papel_clinico("medico")
    def adicionar_exame(uuid_resultado):
        """Adiciona um exame prescrito a um ResultadoPrescricao (rascunho do próprio médico, atendimento
        em andamento); o resultado passa a ser do médico."""
        dados = request.get_json(silent=True) or {}
        try:
            item = ExamePrescritoIn.model_validate(dados)
            pe = _svc_prescricao_exame.adicionar_exame(
                uuid_resultado, item, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return (json_success(data=pe.to_dict(), message="Exame prescrito.", status=201),
                    detalhes(pe.resultado_prescricao))
        except ValidationError as ex:
            return erro(json_error(formatar_erros_pydantic(ex), 422))
        except BionException as ex:
            return erro(json_error(ex.message, ex.status_code))

    @staticmethod
    @bp_prescricao_exame.patch("/<uuid_resultado>/exames/<uuid_item>")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="alterar exame da prescrição", operacao="escrita")
    def atualizar_exame(uuid_resultado, uuid_item):
        """Altera urgência ou justificativa (só o que foi enviado). Se algo mudou, o item e a
        prescrição passam a ser do médico."""
        dados = request.get_json(silent=True) or {}
        try:
            patch = ExamePrescritoPatch.model_validate(dados)
            pe = _svc_prescricao_exame.atualizar_exame(
                uuid_resultado, uuid_item, patch, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return json_success(data=pe.to_dict(), message="Exame atualizado."), detalhes(pe.resultado_prescricao)
        except ValidationError as ex:
            return erro(json_error(formatar_erros_pydantic(ex), 422))
        except BionException as ex:
            return erro(json_error(ex.message, ex.status_code))

    @staticmethod
    @bp_prescricao_exame.delete("/<uuid_resultado>/exames/<uuid_item>")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="remover exame da prescrição", operacao="escrita")
    def remover_exame(uuid_resultado, uuid_item):
        """Remove um exame do rascunho (inclusive sugestões da IA que o médico descartou)."""
        try:
            _svc_prescricao_exame.remover_exame(
                uuid_resultado, uuid_item, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return json_success(message="Exame removido da prescrição."), {}
        except BionException as ex:
            return erro(json_error(ex.message, ex.status_code))