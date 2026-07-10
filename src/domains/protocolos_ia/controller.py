"""Rotas JSON do domínio IA: execução de protocolos, análise via LLM e consulta de resultados (OutputBion)."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import OutputBionService
from .service_llm import OutputBionLlmService

bp_ia = Blueprint("ia", __name__)

_svc_ia = OutputBionService()
_svc_ia_llm = OutputBionLlmService()


@bp_ia.post("/analisar")
@requer_papel("medico", "enfermeiro")
def analisar():
    """Executa um protocolo determinístico (via Strategy/Factory) e persiste o resultado."""
    dados = request.get_json(silent=True) or {}
    sigla = dados.get("sigla_protocolo")
    if not sigla:
        return json_error("sigla_protocolo é obrigatório.", 422)
    try:
        output = _svc_ia.executar_protocolo(
            sigla, dados, id_input_protocolo=dados.get("id_input_protocolo")
        )
        return json_success(data=output.to_dict(), message="Análise da IA concluída.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_ia.post("/analisar-llm")
@requer_papel("medico")
def analisar_llm():
    """Executa a análise clínica via IA generativa (Claude), complementar aos protocolos determinísticos."""
    from .motor.ia_base import ContextoClinico
    dados = request.get_json(silent=True) or {}
    ctx = ContextoClinico(
        sinais_vitais=dados.get("sinais_vitais", []),
        alergias=dados.get("alergias", []),
        doencas=dados.get("doencas", []),
        medicamentos_em_uso=dados.get("medicamentos_em_uso", []),
        resultado_triagem=dados.get("resultado_triagem"),
    )
    try:
        output = _svc_ia_llm.analisar_com_llm(ctx, id_input_protocolo=dados.get("id_input_protocolo"))
        return json_success(data=output.to_dict(), message="Análise da IA (LLM) concluída.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    except Exception:
        return json_error("Erro ao consultar o serviço de IA. Tente novamente.", 502)


@bp_ia.get("/output/<uuid>")
@requer_login
def output_json(uuid):
    """Rota JSON consumida pelo front na tela de triagem."""
    try:
        output = _svc_ia.buscar_por_uuid(uuid)
        return json_success(data=output.output_ia_json)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp_ia.get("/output-triagem/<consulta_uuid>")
@requer_login
def output_triagem_json(consulta_uuid):
    """Rota JSON consumida pelo front na tela médica."""
    try:
        output = _svc_ia.buscar_output_triagem(consulta_uuid)
        return json_success(data=output.output_ia_json)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
