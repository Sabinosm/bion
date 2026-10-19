
from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico
from src.core.consultas import ler_paginacao, resposta_paginada
from .service import CatalogoExamesService

bp_exames = Blueprint("catalogo_exames", __name__)
_svc = CatalogoExamesService()

class ExamesController():
    
    @staticmethod
    @bp_exames.get("/")
    @requer_login
    def lista_exames():
        """Query string: q (nome em português/inglês ou sinônimo), tipo (laboratorial, imagem,
        funcional, outro), pagina, por_pagina. Só exames ativos."""
        pagina, por_pagina = ler_paginacao()
        try:
            resultado = _svc.listar_paginado(request.args.get("q"), request.args.get("tipo"), pagina, por_pagina)
            return json_success(data=resposta_paginada(resultado, lambda e: e.to_dict()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_exames.get("/<uuid>")
    @requer_papel_clinico("medico")
    def detalhe_exame(uuid):
        try:
            e = _svc.buscar_por_uuid(uuid)
            return json_success(data=e.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_exames.post("/")
    @requer_papel_clinico("medico")
    def criar_exame():
        dados = request.get_json(silent=True) or {}
        try:
            e = _svc.criar(dados)
            return json_success(data=e.to_dict(), message="Exame cadastrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

