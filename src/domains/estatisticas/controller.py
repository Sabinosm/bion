from flask import Blueprint, request, session
from src.core.responses import json_success, json_error
from .services.service import EstatisticasService
from src.core.session import requer_papel, get_id_empresa_sessao


bp = Blueprint("estatisticas", __name__)
_svc = EstatisticasService()


@bp.get("/geral")
@requer_papel("admin")
def estatisticas_geral():
    try:
        dados = _svc.estatisticas_geral(get_id_empresa_sessao())
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A1: Volume de atendimentos ---
@bp.get("/atendimentos/volume")
@requer_papel("admin")
def volume_atendimentos():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.volume_atendimentos(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A2: Tempo médio de atendimento ---
@bp.get("/atendimentos/tempo-medio")
@requer_papel("admin")
def tempo_medio_atendimento():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.tempo_medio_atendimento(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A3: Taxa de conclusão vs. abandono ---
@bp.get("/atendimentos/taxa-conclusao")
@requer_papel("admin")
def taxa_conclusao():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.taxa_conclusao(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A4: Efetivo ativo por papel ---
@bp.get("/equipe/efetivo")
@requer_papel("admin")
def efetivo_ativo():
    try:
        dados = _svc.efetivo_ativo(get_id_empresa_sessao())
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D2: Alergias mais reportadas ---
@bp.get("/alergias/top-substancias")
@requer_papel("admin")
def alergias_top_substancias():
    try:
        limite = request.args.get("limite", default=10, type=int)
        dados = _svc.alergias_top_substancias(get_id_empresa_sessao(), limite=limite)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D2 (detalhe): gravidade por substância ---
@bp.get("/alergias/<string:substancia>/gravidade")
@requer_papel("admin")
def alergia_gravidade_por_substancia(substancia):
    try:
        dados = _svc.alergia_gravidade_por_substancia(get_id_empresa_sessao(), substancia=substancia)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A5: Engajamento/atividade da equipe ---
@bp.get("/equipe/engajamento")
@requer_papel("admin")
def engajamento_equipe():
    try:
        dias = request.args.get("dias", default=7, type=int)
        dados = _svc.engajamento_equipe(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D3: Urgência de exames -- IA vs. profissional ---
@bp.get("/exames/urgencia-por-origem")
@requer_papel("admin")
def urgencia_exames_por_origem():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.urgencia_exames_por_origem(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- C1: Doenças mais comuns por região ---
@bp.get("/epidemiologico/top-cid-regiao")
@requer_papel("admin")
def top_cid_por_regiao():
    try:
        dias = request.args.get("dias", default=14, type=int)
        limite = request.args.get("limite", default=10, type=int)
        dados = _svc.top_cid_por_regiao(get_id_empresa_sessao(), dias=dias, limite=limite)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- C3: Incidência por 100 mil habitantes ---
@bp.get("/epidemiologico/incidencia-regiao")
@requer_papel("admin")
def incidencia_por_regiao():
    try:
        dias = request.args.get("dias", default=14, type=int)
        dados = _svc.incidencia_por_regiao(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))