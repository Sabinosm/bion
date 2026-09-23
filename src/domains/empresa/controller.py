"""Rotas JSON do dominio Empresa (tenant)."""

from flask import Blueprint, request


from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, get_uuid_empresa_sessao, get_id_empresa_sessao, requer_super_admin
from .service import EmpresaService
from src.domains.auditoria.acaoSensivel import acao_sensivel

bp = Blueprint("empresa", __name__)
_svc = EmpresaService()

class EmpresaController():
    
    @staticmethod
    @bp.get("/")
    @requer_admin
    def detalhe():
        try:
            e = _svc.repo.find_by_id(get_id_empresa_sessao())
            return json_success(data=e.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.put("/") 
    @requer_super_admin
    @acao_sensivel(acao="atualizar_empresa", tabela="empresa")
    def atualizar():
        uuid = get_uuid_empresa_sessao()
        dados = request.get_json(silent=True) or {}
        try:
            e = _svc.atualizar(get_id_empresa_sessao(), dados, uuid, False)
            resposta = json_success(data=e.to_dict(), message="Empresa atualizada.")
            return resposta, {
                "id_registro": e.id,
                "uuid_registro": e.uuid,
                "operacao": "UPDATE",
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}


    # Para acessar tem que ter pago? TODO pensar em ordem de acesso nesse quesito. 
    # Acho que o certo seria Tela inicial/apresentação planos - pagamento e então criação da empresa.

    @staticmethod
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


    @staticmethod
    @bp.get("/existe-cnpj/<cnpj>")
    def existe_cnpj(cnpj):
        try:
            existe = _svc.cnpj_ja_cadastrado(cnpj)
            return json_success(data={"existe": existe})
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
        
    
    @staticmethod
    @bp.get("/existe-cnes/<cnes>")
    def existe_cnes(cnes):
        try:
            existe = _svc.cnes_ja_cadastrado(cnes)
            return json_success(data={"existe": existe})
        except BionException as ex:
            return json_error(ex.message, ex.status_code)