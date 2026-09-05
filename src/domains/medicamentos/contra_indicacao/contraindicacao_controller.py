from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login
from .contraindicacao_service import ContraindicacaoService

bp_contraindicacoes = Blueprint("contraindicacoes", __name__)
_svc = ContraindicacaoService()


class ContraindicacaoController():

    @staticmethod
    @bp_contraindicacoes.get("/")
    @requer_login
    def lista_contraindicacoes():
        termo = request.args.get("q")
        itens = _svc.buscar_por_nome(termo) if termo else _svc.listar()
        return json_success(data=[c.to_dict() for c in itens])

    @staticmethod
    @bp_contraindicacoes.get("/<uuid>")
    @requer_login
    def detalhe_contraindicacao(uuid):
        try:
            c = _svc.buscar_por_uuid(uuid)
            return json_success(data=c.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_contraindicacoes.get("/<uuid>/medicamentos")
    @requer_login
    def medicamentos_da_contraindicacao(uuid):
        """Ex: médico busca 'gravidez' e vê todos os medicamentos do
        catálogo contraindicados nessa condição."""
        try:
            medicamentos = _svc.medicamentos_da_contraindicacao(uuid)
            return json_success(data=[m.to_dict() for m in medicamentos])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)