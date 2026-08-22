"""Rotas JSON do dominio Empresa (tenant)."""

from flask import Blueprint, request


from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_uuid_empresa_sessao, id_empresa_sessao
from .service import EmpresaService

bp = Blueprint("empresa", __name__)
_svc = EmpresaService()


@bp.get("/")
@requer_papel("admin")
def detalhe():
    try:
        e = _svc.repo.find_by_id(id_empresa_sessao())
        return json_success(data=e.to_dict())
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.put("/") 
@requer_papel("admin")
def atualizar():
    uuid = get_uuid_empresa_sessao()
    dados = request.get_json(silent=True) or {}
    try:
        e = _svc.atualizar(id_empresa_sessao(), dados, uuid)
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


@bp.get("/existe-cnpj/<cnpj>")
def existe_cnpj(cnpj):
    try:
        existe = _svc.cnpj_ja_cadastrado(cnpj)
        return json_success(data={"existe": existe})
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    
@bp.get("/existe-cnes/<cnes>")
def existe_cnes(cnes):
    try:
        existe = _svc.cnes_ja_cadastrado(cnes)
        return json_success(data={"existe": existe})
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
    

