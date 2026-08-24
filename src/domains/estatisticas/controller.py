from flask import Blueprint, request, session
from src.core.responses import json_success, json_error
from .services.service import EstatisticasService
from src.core.session import requer_papel, get_id_empresa_sessao


bp = Blueprint("estatisticas", __name__)
_svc = EstatisticasService()


@bp.get("/geral")
@requer_papel("admin")
def estatisticas_geral():
    return _svc.estatisticas_geral(get_id_empresa_sessao())


# --- A1: Volume de atendimentos ---
@bp.get("/atendimentos/volume")
@requer_papel("admin")
def volume_atendimentos():
    dias = request.args.get("dias", default=30, type=int)
    return _svc.volume_atendimentos(get_id_empresa_sessao(), dias=dias)


# --- A2: Tempo médio de atendimento ---
@bp.get("/atendimentos/tempo-medio")
@requer_papel("admin")
def tempo_medio_atendimento():
    dias = request.args.get("dias", default=30, type=int)
    return _svc.tempo_medio_atendimento(get_id_empresa_sessao(), dias=dias)


# --- A3: Taxa de conclusão vs. abandono ---
@bp.get("/atendimentos/taxa-conclusao")
@requer_papel("admin")
def taxa_conclusao():
    dias = request.args.get("dias", default=30, type=int)
    return _svc.taxa_conclusao(get_id_empresa_sessao(), dias=dias)


# --- A4: Efetivo ativo por papel ---
@bp.get("/equipe/efetivo")
@requer_papel("admin")
def efetivo_ativo():
    return _svc.efetivo_ativo(get_id_empresa_sessao())