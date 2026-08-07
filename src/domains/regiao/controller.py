"""Rotas JSON do dominio Regiao Geografica."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import RegiaoService

bp = Blueprint("regiao", __name__)
_svc = RegiaoService()


@bp.get("/")
@requer_login
def lista():
    tipo = request.args.get("tipo")
    itens = _svc.listar(tipo)
    return json_success(data=[r.to_dict() for r in itens])


@bp.get("/<uuid>")
@requer_login
def detalhe(uuid):
    try:
        r = _svc.buscar_por_uuid(uuid)
        return json_success(data=r.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/codigo/<codigo_ibge>")
def detalhe_por_código(codigo_ibge: str):
    """
    ALTERADO: antes só buscava no banco (404 se não achasse). Agora,
    se o código não existir localmente, tenta confirmar e cadastrar
    via API do IBGE antes de desistir -- só retorna 404 de fato se o
    código também não existir no IBGE (ou se a consulta externa falhar).
    """
    try:
        r = _svc.buscar_ou_criar_por_codigo_ibge(codigo_ibge)
        if not r:
            return json_error(f"Região geográfica não encontrada: {codigo_ibge}", 404)
        return json_success(data=r.to_dict())

    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    

@bp.get("/regiao/<cep>")
def detalhe_por_cep(cep: str):
    """
    Consulta a região geográfica correspondente ao CEP informado. 
    """
    
    from src.domains.regiao.cep_service import CepService
    from src.domains.regiao.service import RegiaoService
            
    cps = CepService()
    codigo_ibge = cps.buscar_codigo_ibge_por_cep(cep)
            
    regiao_service = RegiaoService()
    regiao = regiao_service.buscar_por_código(codigo_ibge) if codigo_ibge else None
    
    if regiao:
        return regiao.to_dict()
    else:
        return json_error(f"Região geográfica não encontrada para o CEP: {cep}", 404)
    
    