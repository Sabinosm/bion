from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico
from src.core.consultas import ler_paginacao, resposta_paginada
from .service import CatalogoMedicamentosService

bp_medicamentos = Blueprint("catalogo_medicamentos", __name__)
_svc = CatalogoMedicamentosService()

class MedicamentosController():

    @staticmethod
    @bp_medicamentos.get("/")
    @requer_login
    def lista_medicamentos():
        """Query string: q (busca por princípio ativo), pagina, por_pagina."""
        pagina, por_pagina = ler_paginacao()
        resultado = _svc.listar_paginado(request.args.get("q"), pagina, por_pagina)
        return json_success(data=resposta_paginada(resultado, lambda m: m.to_dict()))


    @staticmethod
    @bp_medicamentos.get("/<uuid>")
    @requer_login
    def detalhe_medicamento(uuid):
        try:
            m = _svc.buscar_por_uuid(uuid)
            return json_success(data=m.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_medicamentos.get("/<uuid>/interacoes")
    @requer_papel_clinico("medico")
    def interacoes_medicamento(uuid):
        try:
            resultado = _svc.verificar_interacoes(uuid)
            total = resultado["total_na_base"]
            aviso = (
                "Base de interações ainda vazia."
                if total == 0 else
                "Lista vazia não significa ausência de interação clínica: "
                "a base cobre apenas as interações cadastradas."
            )
            return json_success(data={
                "interacoes": [i.to_dict() for i in resultado["interacoes"]],
                "cobertura": {
                    "total_interacoes_na_base": total,
                    "aviso": aviso,
                },
            })
        except BionException as ex:
            return json_error(ex.message, ex.status_code)