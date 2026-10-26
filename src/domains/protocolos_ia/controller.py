"""Rotas JSON do domínio de IA: execução de protocolos, análise por LLM e consulta de resultados (OutputBion).

Este arquivo recebe a requisição HTTP, extrai o autor da sessão, delega ao serviço e traduz o resultado ou a exceção em JSON.
"""
from __future__ import annotations

import logging

from flask import Blueprint, request

from src.core.exceptions import BionException
from src.core.responses import json_error, json_success
from src.core.session import (
    get_funcao_clinica_sessao,
    get_id_empresa_sessao,
    get_id_usuario_sessao,
    requer_login,
    requer_papel_clinico,
)
from src.models import db

from .application.dto.analysis_request import LLMAnalysisRequest
from .application.ports.output_repository import AutorRequisicao
from .composicao import montar_servico_llm
from .service import OutputBionService

logger = logging.getLogger("bion.ia.controller")

bp_ia = Blueprint("ia", __name__)

_svc_ia = OutputBionService()
_fabrica_servico_llm = montar_servico_llm


def _autor() -> AutorRequisicao:
    return AutorRequisicao(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


class IaController():

    @staticmethod
    @bp_ia.post("/analisar")
    @requer_papel_clinico("medico", "enfermeiro")
    def analisar():
        """Executa um protocolo determinístico (via Strategy/Factory). Com id_input_protocolo, persiste o resultado."""
        dados = request.get_json(silent=True) or {}
        if not isinstance(dados, dict):
            return json_error("O corpo da requisição deve ser um objeto JSON.", 422)
        sigla = dados.get("sigla_protocolo")
        if not sigla or not isinstance(sigla, str):
            return json_error("sigla_protocolo é obrigatório.", 422)
        try:
            resultado = _svc_ia.executar_protocolo(
                sigla, dados, id_input_protocolo=dados.get("id_input_protocolo"), autor=_autor()
            )
            persistido = resultado["persistido"]
            return json_success(
                data=resultado,
                message="Análise da IA concluída.",
                status=201 if persistido else 200,
            )
        except BionException as ex:
            db.session.rollback()
            return json_error(ex.message, ex.status_code, ex.erros)

    @staticmethod
    @bp_ia.post("/analisar-llm")
    @requer_papel_clinico("medico")
    def analisar_llm():
        """Executa a análise clínica por IA generativa, complementar aos protocolos determinísticos.

        Com id_input_protocolo o contexto vem do snapshot do atendimento e a resposta é persistida.
        Sem ele, a análise é avulsa e nada é gravado. Falha da IA devolve fallback com llm_disponivel=false.
        """
        try:
            requisicao = LLMAnalysisRequest.de_corpo_http(request.get_json(silent=True))
            resultado = _fabrica_servico_llm().analisar(requisicao, _autor())
            mensagem = (
                "Análise da IA (LLM) concluída."
                if resultado.llm_disponivel
                else "Análise da IA (LLM) indisponível; os protocolos determinísticos permanecem válidos."
            )
            return json_success(data=resultado.para_resposta_http(), message=mensagem, status=201)
        except BionException as ex:
            db.session.rollback()
            return json_error(ex.message, ex.status_code, ex.erros)
        except Exception as exc:
            db.session.rollback()
            logger.error("erro_interno_analise_llm", extra={"tipo_erro": type(exc).__name__})
            return json_error("Erro interno ao processar a análise de IA.", 500)

    @staticmethod
    @bp_ia.get("/output/<uuid>")
    @requer_login
    def output_json(uuid):
        """Rota JSON consumida pelo front na tela de triagem."""
        try:
            output = _svc_ia.buscar_por_uuid(uuid, get_id_empresa_sessao())
            return json_success(data=output.output_ia_json)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_ia.get("/output-triagem/<consulta_uuid>")
    @requer_login
    def output_triagem_json(consulta_uuid):
        """Rota JSON consumida pelo front na tela médica."""
        try:
            output = _svc_ia.buscar_output_triagem(consulta_uuid, get_id_empresa_sessao())
            return json_success(data=output.output_ia_json)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
