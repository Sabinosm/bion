
from flask import Blueprint, request, session
from src.core.responses import json_success, json_error
from .services.service  import EstatisticasService
from src.core.session import requer_papel, get_id_empresa_sessao


bp = Blueprint("estatisticas", __name__)
_svc = EstatisticasService()

@bp.get("/geral")
@requer_papel("admin")
def estatisticas_geral():
    
    pass