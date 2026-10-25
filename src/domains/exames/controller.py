from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException, DadosInvalidosError
from src.core.session import requer_login, requer_papel_clinico
from src.core.consultas import ler_paginacao, resposta_paginada
from .service import CatalogoExamesService

bp_exames = Blueprint("catalogo_exames", __name__)
_svc = CatalogoExamesService()


def _ler_bool(nome):
    """None se ausente; True/False para 'true'/'false' (qualquer caixa); erro nos demais."""
    bruto = request.args.get(nome)
    if bruto is None or not bruto.strip():
        return None
    valor = bruto.strip().lower()
    if valor in ("true", "1"):
        return True
    if valor in ("false", "0"):
        return False
    raise DadosInvalidosError(f"{nome} deve ser true ou false.")


class ExamesController():

    @staticmethod
    @bp_exames.get("/")
    @requer_login
    def lista_exames():
        """Query string: q (nome em português/inglês ou sinônimo), tipo (laboratorial, imagem,
        funcional, outro), material, exige_jejum (true/false), pagina, por_pagina.
        Só exames ativos."""
        pagina, por_pagina = ler_paginacao()
        try:
            resultado = _svc.listar_paginado(
                request.args.get("q"), request.args.get("tipo"), pagina, por_pagina,
                material=request.args.get("material"),
                exige_jejum=_ler_bool("exige_jejum"),
            )
            return json_success(data=resposta_paginada(resultado, lambda e: e.to_dict()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_exames.get("/filtros")
    @requer_login
    def filtros_exames():
        """Valores para popular os filtros: tipos e materiais existentes."""
        return json_success(data=_svc.listar_filtros())


    @staticmethod
    @bp_exames.get("/<uuid>")
    @requer_papel_clinico("medico")
    def detalhe_exame(uuid):
        try:
            e = _svc.buscar_por_uuid(uuid)
            return json_success(data=e.to_dict_detalhe())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_exames.get("/<uuid>/conteudo")
    @requer_papel_clinico("medico")
    def conteudo_exame(uuid):
        """Conteúdo de apoio (MedlinePlus) já guardado. Query string: idioma (en|es, padrão en).
        Sem conteúdo: 200 com disponivel=false."""
        try:
            return json_success(data=_svc.conteudo_de_apoio(uuid, request.args.get("idioma", "en")))
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