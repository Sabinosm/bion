"""Rotas JSON do dominio Empresa (tenant)."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from .service import EmpresaService

bp = Blueprint("empresa", __name__)
_svc = EmpresaService()

# Por que o admin recebe a lista de todas as empresas? Deveria ser os dados da empresa dele não faz sentido
@bp.get("/")
@requer_papel("admin")
def lista():
    itens = _svc.listar()
    return json_success(data=[e.to_dict() for e in itens])


@bp.get("/<uuid>")
@requer_login
def detalhe(uuid):
    try:
        e = _svc.buscar_por_uuid(uuid)
        return json_success(data=e.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.put("/<uuid>")
@requer_papel("admin")
def atualizar(uuid):
    dados = request.get_json(silent=True) or {}
    try:
        e = _svc.atualizar(uuid, dados)
        return json_success(data=e.to_dict(), message="Empresa atualizada.")
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


# Para acessar tem que ter pago? TODO pensar em ordem de acesso nesse quesito. 
# Acho que o certo seria Tela inicial/apresentação planos - pagamento e então criação da empresa.

@bp.post("/create")
def criar():
    dados = request.get_json(silent=True) or {}
    dados_empresa = dados.get('empresa', {})
    dados_admin = dados.get('admin', {})
    try:
        e,a = _svc.cadastrar_com_admin(dados_empresa,dados_admin)
        return json_success(data={"empresa":e.to_dict(), "admin": a.to_dict()}, message="Empresa e admin criados com sucesso.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


