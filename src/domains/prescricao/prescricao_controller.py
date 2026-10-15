"""Rotas JSON da entidade Prescricao: medicamentos prescritos."""

from flask import Blueprint, request
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao
from .prescricao_service import PrescricaoService
from .schema_prescricoes import MedicamentoPrescritoIn, formatar_erros_pydantic

bp_prescricao = Blueprint("prescricao", __name__)
_svc_prescricao = PrescricaoService()

class PrescricaoController():
    @staticmethod
    @bp_prescricao.post("/<uuid_resultado>/medicamentos")
    @requer_papel_clinico("medico")
    def adicionar_medicamento(uuid_resultado):
        """Adiciona um medicamento prescrito a um ResultadoPrescricao (rascunho do próprio médico)."""
        dados = request.get_json(silent=True) or {}
        try:
            item = MedicamentoPrescritoIn.model_validate(dados)
            p = _svc_prescricao.adicionar_medicamento(
                uuid_resultado, item, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return json_success(data=p.to_dict(), message="Medicamento prescrito.", status=201)
        except ValidationError as ex:
            return json_error(formatar_erros_pydantic(ex), 422)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_prescricao.delete("/<uuid_resultado>/medicamentos/<uuid_item>")
    @requer_papel_clinico("medico")
    def remover_medicamento(uuid_resultado, uuid_item):
        """Remove um medicamento do rascunho (inclusive sugestões da IA que o médico descartou)."""
        try:
            _svc_prescricao.remover_medicamento(
                uuid_resultado, uuid_item, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return json_success(message="Medicamento removido da prescrição.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)