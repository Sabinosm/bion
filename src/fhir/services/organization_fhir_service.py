"""Service de orquestração FHIR para Organization. Só OUTBOUND."""

from src.core.exceptions import RecursoNaoEncontradoError
from ._helpers import aplicar_elements


class OrganizationFhirService:
    def __init__(self):
        from src.domains.empresa.repository import EmpresaRepository
        self.repo = EmpresaRepository()

    def buscar_por_id(self, id_fhir: str, elements: list[str] | None = None) -> dict:
        from ..mappers.organization_mapper import empresa_to_fhir_organization
        empresa = self.repo.find_by_uuid(id_fhir)
        if not empresa:
            raise RecursoNaoEncontradoError(f"Organization não encontrado: {id_fhir}")
        return aplicar_elements(empresa_to_fhir_organization(empresa), elements)
