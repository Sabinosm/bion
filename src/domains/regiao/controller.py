"""Rotas JSON do dominio Regiao Geografica."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login
from .service import RegiaoService

bp = Blueprint("regiao", __name__)
_svc = RegiaoService()

class RegiaoController():
    
    @staticmethod
    @bp.get("/")
    @requer_login
    def lista():
        tipo = request.args.get("tipo")
        itens = _svc.listar(tipo)
        return json_success(data=[r.to_dict() for r in itens])


    
    @staticmethod
    @bp.get("/uuid/<uuid>")
    @requer_login
    def detalhe(uuid):
        """
        Retorna os detalhes de uma região geográfica pelo UUID.
        """
        try:
            r = _svc.buscar_por_uuid(uuid)
            return json_success(data=r.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    
    @staticmethod
    @bp.get("/codigo/<codigo_ibge>")
    @requer_login
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
        

    
    @staticmethod
    @bp.get("/cep/<cep>")
    @requer_login
    def detalhe_por_cep(cep: str):
        """
        Consulta a região geográfica correspondente ao CEP informado. 
        """
        
        from src.domains.regiao.cep_service import CepService
                
        cps = CepService()
        regiao = cps.regiao_por_cep(cep)
        
        if regiao:
            return regiao.to_dict()
        else:
            return json_error(f"Região geográfica não encontrada para o CEP: {cep}", 404)
        
        