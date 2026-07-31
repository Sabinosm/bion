"""
Rotas FHIR para AllergyIntolerance. Agora com INBOUND (POST) além do
outbound (GET) que já existia.
"""

from flask import Blueprint, request
from pydantic import ValidationError
from fhir.resources.R4B.allergyintolerance import AllergyIntolerance

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from src.fhir.services.allergyintolerance_fhir_service import AllergyIntoleranceFhirService

bp = Blueprint("fhir_allergyintolerance", __name__)
_svc = AllergyIntoleranceFhirService()


def _parse_elements() -> list[str] | None:
    raw = request.args.get("_elements")
    return raw.split(",") if raw else None


@bp.get("/AllergyIntolerance/<id_fhir>")
@requer_login
def read(id_fhir):
    try:
        recurso = _svc.buscar_por_id(id_fhir, elements=_parse_elements())
        return json_success(data=recurso)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/AllergyIntolerance")
@requer_login
def search():
    """GET /fhir/AllergyIntolerance?patient={uuid_paciente}"""
    uuid_paciente = request.args.get("patient")
    if not uuid_paciente:
        return json_error("Parâmetro 'patient' obrigatório.", 422)
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


@bp.post("/AllergyIntolerance")
@requer_papel("medico", "enfermeiro")
def create():
    """POST /fhir/AllergyIntolerance -- NOVO (inbound).

    Diferente de Practitioner, este recurso NÃO precisa de parâmetros
    extras fora do corpo FHIR -- patient.reference já identifica o
    paciente, e reaction[] já traz manifestação/gravidade/descrição.
    """
    payload = request.get_json(silent=True) or {}

    try:
        allergy = AllergyIntolerance(**payload)
    except ValidationError as e:
        return json_error(f"Recurso AllergyIntolerance inválido: {e}", 422)

    try:
        recurso = _svc.criar_a_partir_de_fhir(allergy)
        return json_success(data=recurso, message="AllergyIntolerance criada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
