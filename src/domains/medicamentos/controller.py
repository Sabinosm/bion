from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico
from src.core.consultas import ler_paginacao, resposta_paginada
from .service import CatalogoMedicamentosService

bp_medicamentos = Blueprint("catalogo_medicamentos", __name__)
_svc = CatalogoMedicamentosService()


def _ler_lista(nome):
    """Aceita ?x=a&x=b e ?x=a,b (e mistura dos dois)."""
    valores = []
    for bruto in request.args.getlist(nome):
        valores.extend(p.strip() for p in bruto.split(",") if p.strip())
    return valores


def _medicamento_resumido(m):
    return {"uuid": m.uuid, "principio_ativo": m.principio_ativo}


def _interacao_para_dict(i):
    """to_dict da interação + os dois medicamentos envolvidos
    (sem isso o front não sabe qual é o outro lado da interação)."""
    d = i.to_dict()
    d["medicamento_a"] = _medicamento_resumido(i.medicamento_a)
    d["medicamento_b"] = _medicamento_resumido(i.medicamento_b)
    return d


def _cobertura(total):
    aviso = (
        "Base de interações ainda vazia."
        if total == 0 else
        "Lista vazia não significa ausência de interação clínica: "
        "a base cobre apenas as interações cadastradas."
    )
    return {"total_interacoes_na_base": total, "aviso": aviso}


class MedicamentosController():

    @staticmethod
    @bp_medicamentos.get("/")
    @requer_login
    def lista_medicamentos():
        """Query string: q (princípio ativo, sinônimo ou nome comercial),
        indicacao (uuid), sem_contraindicacao (uuid; repetível ou separado por vírgula),
        classe (classe farmacêutica exata), pagina, por_pagina."""
        pagina, por_pagina = ler_paginacao()
        try:
            resultado = _svc.listar_paginado(
                request.args.get("q"), pagina, por_pagina,
                uuid_indicacao=request.args.get("indicacao"),
                uuids_sem_contraindicacao=_ler_lista("sem_contraindicacao"),
                classe=request.args.get("classe"),
            )
            return json_success(data=resposta_paginada(resultado, lambda m: m.to_dict_resumo()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_medicamentos.get("/classes")
    @requer_login
    def lista_classes():
        """Classes farmacêuticas existentes, para popular o filtro."""
        return json_success(data=_svc.listar_classes())


    @staticmethod
    @bp_medicamentos.get("/<uuid>")
    @requer_login
    def detalhe_medicamento(uuid):
        try:
            m = _svc.buscar_por_uuid(uuid)
            return json_success(data=m.to_dict_detalhe())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_medicamentos.get("/<uuid>/interacoes")
    @requer_papel_clinico("medico")
    def interacoes_medicamento(uuid):
        try:
            resultado = _svc.verificar_interacoes(uuid)
            return json_success(data={
                "interacoes": [_interacao_para_dict(i) for i in resultado["interacoes"]],
                "cobertura": _cobertura(resultado["total_na_base"]),
            })
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp_medicamentos.post("/interacoes/verificar")
    @requer_papel_clinico("medico")
    def verificar_interacoes_entre():
        """Body: {"medicamentos": [uuid, uuid, ...]} -- o que está sendo prescrito
        mais o que o paciente já usa. Devolve as interações entre eles."""
        dados = request.get_json(silent=True) or {}
        uuids = dados.get("medicamentos")
        if not isinstance(uuids, list) or not all(isinstance(u, str) for u in uuids):
            return json_error("medicamentos deve ser uma lista de uuids.", 400)
        try:
            resultado = _svc.verificar_interacoes_entre(uuids)
            return json_success(data={
                "medicamentos": [_medicamento_resumido(m) for m in resultado["medicamentos"]],
                "interacoes": [_interacao_para_dict(i) for i in resultado["interacoes"]],
                "cobertura": _cobertura(resultado["total_na_base"]),
            })
        except BionException as ex:
            return json_error(ex.message, ex.status_code)