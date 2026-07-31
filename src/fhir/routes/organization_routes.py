"""Rotas FHIR para Organization (br-core-organization). Só OUTBOUND por ora."""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login
from ..services.organization_fhir_service import OrganizationFhirService

bp = Blueprint("fhir_organization", __name__)
_svc = OrganizationFhirService()


def _parse_elements() -> list[str] | None:
    raw = request.args.get("_elements")
    return raw.split(",") if raw else None


@bp.get("/Organization/<id_fhir>")
@requer_login
def read(id_fhir):
    """GET /fhir/Organization/{id}"""
    try:
        recurso = _svc.buscar_por_id(id_fhir, elements=_parse_elements())
        return json_success(data=recurso)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)
