"""
Rotas FHIR para Practitioner (br-core-practitioner).

REESCRITO para usar fhir.resources.R4B: a validação de forma do
recurso agora é feita construindo a classe Practitioner da biblioteca
diretamente a partir do JSON recebido (Practitioner(**payload)),
substituindo o schema Pydantic manual que tínhamos antes -- a lib já
sabe quais campos são obrigatórios e a estrutura correta, direto da
StructureDefinition oficial.

ATENÇÃO SOBRE AUTENTICAÇÃO: mesma ressalva de antes -- @requer_login
por ora, migrar para SMART on FHIR se for consumido por sistemas
externos de verdade.
"""

from flask import Blueprint, request
from pydantic import ValidationError
from fhir.resources.R4B.practitioner import Practitioner

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_empresa_sessao
from ..services.practitioner_fhir_service import PractitionerFhirService

bp = Blueprint("fhir_practitioner", __name__)
_svc = PractitionerFhirService()


def _parse_elements() -> list[str] | None:
    raw = request.args.get("_elements")
    return raw.split(",") if raw else None


@bp.get("/Practitioner/<id_fhir>")
@requer_login
def read(id_fhir):
    """GET /fhir/Practitioner/{id}"""
    try:
        recurso = _svc.buscar_por_id(id_fhir, elements=_parse_elements())
        return json_success(data=recurso)
    except BionException as ex:
        return json_error(ex.message, ex.status_code)


@bp.get("/Practitioner")
@requer_login
def search():
    """GET /fhir/Practitioner?identifier=system|value -- busca convencional FHIR."""
    identifier_param = request.args.get("identifier")
    if not identifier_param or "|" not in identifier_param:
        return json_error("Parâmetro 'identifier' obrigatório, no formato system|value.", 422)
    sistema, valor = identifier_param.split("|", 1)
    resultados = _svc.buscar_por_identifier(sistema, valor)

    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(resultados),
        "entry": [{"resource": r} for r in resultados],
    }
    return json_success(data=bundle)


@bp.post("/Practitioner")
@requer_papel("admin")
def create():
    """POST /fhir/Practitioner -- cria um Practitioner a partir do envelope FHIR.

    LIMITAÇÃO CONHECIDA (mantida, documentada em README_RECEBIMENTO.md):
    o Resource Practitioner puro não carrega tipo_usuario, user_login,
    nem CRM/COREN completos -- só funciona hoje para tipo_usuario=admin.
    """
    payload = request.get_json(silent=True) or {}
    tipo_usuario = request.args.get("tipo_usuario")
    user_login = request.args.get("user_login")

    if tipo_usuario not in ("medico", "enfermeiro", "admin"):
        return json_error(
            "Query param 'tipo_usuario' obrigatório (medico|enfermeiro|admin) -- "
            "não faz parte do Resource Practitioner padrão.", 422
        )
    if not user_login:
        return json_error(
            "Query param 'user_login' obrigatório -- não faz parte "
            "do Resource Practitioner padrão.", 422
        )

    try:
        # Practitioner(**payload) já valida resourceType, cardinalidade
        # e tipos de todos os campos, direto da spec oficial R4B.
        practitioner = Practitioner(**payload)
    except ValidationError as e:
        return json_error(f"Recurso Practitioner inválido: {e}", 422)

    try:
        recurso = _svc.criar_a_partir_de_fhir(practitioner, get_id_empresa_sessao(), tipo_usuario, user_login)
        return json_success(data=recurso, message="Practitioner criado.", status=201)
    except (BionException, ValueError) as ex:
        message = ex.message if isinstance(ex, BionException) else str(ex)
        status = ex.status_code if isinstance(ex, BionException) else 422
        return json_error(message, status)
