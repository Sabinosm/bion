"""Rotas JSON da entidade ResultadoPrescricao: diagnóstico e desfecho clínico."""

from flask import Blueprint, request
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_login, requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao,
)
from .resultado_prescricao_service import ResultadoPrescricaoService
from ..schema_prescricoes import ResultadoPrescricaoIn, formatar_erros_pydantic

bp_resultado_prescricao = Blueprint("resultado_prescricao", __name__)
_svc_resultado = ResultadoPrescricaoService()

class ResultadoPrescricaoController():

    @staticmethod
    @bp_resultado_prescricao.post("/atendimento/<uuid_atendimento>")
    @requer_papel_clinico("medico")
    def registrar_resultado(uuid_atendimento):
        """Registra (em rascunho) o diagnóstico (CID-10) e desfecho de um Atendimento."""
        dados = request.get_json(silent=True) or {}
        try:
            d = ResultadoPrescricaoIn.model_validate(dados)
            r = _svc_resultado.registrar_resultado(uuid_atendimento, d, get_id_usuario_sessao())
            return json_success(data=r.to_dict(), message="Resultado de prescrição registrado (rascunho).", status=201)
        except ValidationError as ex:
            return json_error(formatar_erros_pydantic(ex), 422)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_resultado_prescricao.get("/<uuid_resultado>")
    @requer_login
    def detalhe_resultado(uuid_resultado):
        """Retorna os detalhes de um ResultadoPrescricao (com itens) pelo UUID, só da própria empresa."""
        try:
            r = _svc_resultado.buscar_resultado_por_uuid(uuid_resultado, get_id_empresa_sessao())
            return json_success(data=r.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_resultado_prescricao.post("/<uuid_resultado>/confirmar")
    @requer_papel_clinico("medico")
    def confirmar_resultado(uuid_resultado):
        """O médico responsável confirma a prescrição (rascunho -> confirmado)."""
        try:
            r = _svc_resultado.confirmar(uuid_resultado, get_id_empresa_sessao(), get_id_usuario_sessao())
            return json_success(data=r.to_dict(), message="Prescrição confirmada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)