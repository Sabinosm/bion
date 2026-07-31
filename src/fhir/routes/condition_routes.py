"""Rotas FHIR para Condition (br-core-condition / doença crônica)."""

from flask import Blueprint, request
from pydantic import ValidationError
from fhir.resources.R4B.condition import Condition

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from ..services.condition_fhir_service import ConditionFhirService

bp = Blueprint("fhir_condition", __name__)
_svc = ConditionFhirService()


def _parse_elements() -> list[str] | None:
    raw = request.args.get("_elements")
    return raw.split(",") if raw else None


@bp.get("/Condition/<id_fhir>")
@requer_login
def read(id_fhir):
    try:
        recurso = _svc.buscar_por_id(id_fhir, elements=_parse_elements())
        return json_success(data=recurso)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/Condition")
@requer_login
def search():
    """GET /fhir/Condition?subject={uuid_paciente}

    Usa 'subject' no query param, seguindo a convenção real do FHIR
    para este Resource (diferente de AllergyIntolerance, que usa 'patient').
    """
    uuid_paciente = request.args.get("subject")
    if not uuid_paciente:
        return json_error("Parâmetro 'subject' obrigatório.", 422)
    try:
        resultados = _svc.buscar_por_paciente(uuid_paciente)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)

    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(resultados),
        "entry": [{"resource": r} for r in resultados],
    }
    return json_success(data=bundle)


@bp.post("/Condition")
@requer_papel("medico", "enfermeiro")
def create():
    """POST /fhir/Condition -- NOVO (inbound)."""
    payload = request.get_json(silent=True) or {}

    try:
        condition = Condition(**payload)
    except ValidationError as e:
        return json_error(f"Recurso Condition inválido: {e}", 422)

    try:
        recurso = _svc.criar_a_partir_de_fhir(condition)
        return json_success(data=recurso, message="Condition criada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
