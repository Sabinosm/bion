from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login
from .indicacao_terapeutica_service import IndicacaoTerapeuticaService

bp_indicacoes = Blueprint("indicacoes_terapeuticas", __name__)
_svc = IndicacaoTerapeuticaService()


class IndicacaoTerapeuticaController():

    @staticmethod
    @bp_indicacoes.get("/")
    @requer_login
    def lista_indicacoes():
        termo = request.args.get("q")
        itens = _svc.buscar_por_nome(termo) if termo else _svc.listar()
        return json_success(data=[i.to_dict() for i in itens])

    @staticmethod
    @bp_indicacoes.get("/<uuid>")
    @requer_login
    def detalhe_indicacao(uuid):
        try:
            i = _svc.buscar_por_uuid(uuid)
            return json_success(data=i.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_indicacoes.get("/<uuid>/medicamentos")
    @requer_login
    def medicamentos_da_indicacao(uuid):
        """Endpoint central do caso de uso original: médico busca por
        sintoma (ex: 'dor de cabeça') e recebe os medicamentos ligados."""
        try:
            medicamentos = _svc.medicamentos_da_indicacao(uuid)
            return json_success(data=[m.to_dict() for m in medicamentos])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)