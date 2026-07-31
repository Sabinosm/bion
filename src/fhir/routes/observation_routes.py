"""Rotas FHIR para Observation (sinais vitais)."""

from flask import Blueprint, request
from pydantic import ValidationError
from fhir.resources.R4B.observation import Observation

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, g
from ..services.observation_fhir_service import ObservationFhirService

bp = Blueprint("fhir_observation", __name__)
_svc = ObservationFhirService()


def _parse_elements() -> list[str] | None:
    raw = request.args.get("_elements")
    return raw.split(",") if raw else None


@bp.get("/Observation/<id_fhir>")
@requer_login
def read(id_fhir):
    try:
        recurso = _svc.buscar_por_id(id_fhir, elements=_parse_elements())
        return json_success(data=recurso)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/Observation")
@requer_login
def search():
    """GET /fhir/Observation?encounter={uuid_atendimento}"""
    uuid_atendimento = request.args.get("encounter")
    if not uuid_atendimento:
        return json_error("Parâmetro 'encounter' obrigatório.", 422)
    try:
        resultados = _svc.buscar_por_atendimento(uuid_atendimento)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)

    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(resultados),
        "entry": [{"resource": r} for r in resultados],
    }
    return json_success(data=bundle)


@bp.post("/Observation")
@requer_papel("medico", "enfermeiro")
def create():
    """POST /fhir/Observation -- NOVO (inbound).

    Exige encounter.reference apontando para um Atendimento já
    existente -- não cria atendimento novo a partir de uma Observation
    isolada (ver mapper para detalhes).
    """
    payload = request.get_json(silent=True) or {}

    try:
        obs = Observation(**payload)
    except ValidationError as e:
        return json_error(f"Recurso Observation inválido: {e}", 422)

    try:
        recurso = _svc.criar_a_partir_de_fhir(obs, g.id_usuario)
        return json_success(data=recurso, message="Observation criada.", status=201)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
