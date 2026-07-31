"""Rotas FHIR para Patient (br-core-patient)."""

from flask import Blueprint, request, g
from pydantic import ValidationError
from fhir.resources.R4B.patient import Patient

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel
from ..services.patient_fhir_service import PatientFhirService

bp = Blueprint("fhir_patient", __name__)
_svc = PatientFhirService()


def _parse_elements() -> list[str] | None:
    raw = request.args.get("_elements")
    return raw.split(",") if raw else None


@bp.get("/Patient/<id_fhir>")
@requer_login
def read(id_fhir):
    try:
        recurso = _svc.buscar_por_id(id_fhir, elements=_parse_elements())
        return json_success(data=recurso)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.post("/Patient")
@requer_papel("medico", "enfermeiro")
def create():
    """POST /fhir/Patient?consentimento_versao={v}&consentimento_canal={c} -- NOVO (inbound).

    LIMITAÇÃO CONHECIDA (documentada): consentimento LGPD é exigido
    como query param, não como Resource Consent no corpo -- decisão
    pragmática (Opção B do planejamento) em vez de exigir Bundle.
    """
    payload = request.get_json(silent=True) or {}
    consentimento_versao = request.args.get("consentimento_versao")
    consentimento_canal = request.args.get("consentimento_canal")

    try:
        patient = Patient(**payload)
    except ValidationError as e:
        return json_error(f"Recurso Patient inválido: {e}", 422)

    try:
        recurso = _svc.criar_a_partir_de_fhir(
            patient, g.id_usuario, consentimento_versao, consentimento_canal
        )
        return json_success(data=recurso, message="Patient criado.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
