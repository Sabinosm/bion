"""Rotas FHIR para MedicationStatement (br-core-medicationstatement)."""

from flask import Blueprint, request
from pydantic import ValidationError
from fhir.resources.R4B.medicationstatement import MedicationStatement

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from ..services.medicationstatement_fhir_service import MedicationStatementFhirService

bp = Blueprint("fhir_medicationstatement", __name__)
_svc = MedicationStatementFhirService()


def _parse_elements() -> list[str] | None:
    raw = request.args.get("_elements")
    return raw.split(",") if raw else None


@bp.get("/MedicationStatement/<id_fhir>")
@requer_login
def read(id_fhir):
    try:
        recurso = _svc.buscar_por_id(id_fhir, elements=_parse_elements())
        return json_success(data=recurso)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/MedicationStatement")
@requer_login
def search():
    """GET /fhir/MedicationStatement?subject={uuid_paciente}"""
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


@bp.post("/MedicationStatement")
@requer_papel("medico", "enfermeiro")
def create():
    """POST /fhir/MedicationStatement -- NOVO (inbound).

    Aceita tanto medicationReference (medicamento já no catálogo)
    quanto medicationCodeableConcept (texto livre, sem catálogo) --
    ver decisão de política documentada no mapper.
    """
    payload = request.get_json(silent=True) or {}

    try:
        ms = MedicationStatement(**payload)
    except ValidationError as e:
        return json_error(f"Recurso MedicationStatement inválido: {e}", 422)

    try:
        recurso = _svc.criar_a_partir_de_fhir(ms)
        return json_success(data=recurso, message="MedicationStatement criado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
