"""Service de orquestração FHIR para Condition (doença crônica)."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ._helpers import aplicar_elements
from ..mappers.condition_mapper import doenca_to_fhir_condition, fhir_condition_to_dados


class ConditionFhirService:
    def __init__(self):
        from src.domains.paciente.repositories import DoencaCronicaRepository, PacienteRepository
        self.repo = DoencaCronicaRepository()
        self.paciente_repo = PacienteRepository()

    def buscar_por_id(self, id_fhir: str, elements: list[str] | None = None) -> dict:
        doenca = self.repo.find_by_uuid(id_fhir)
        if not doenca:
            raise RecursoNaoEncontradoError(f"Condition não encontrada: {id_fhir}")
        recurso = doenca_to_fhir_condition(doenca)
        return aplicar_elements(recurso.model_dump(exclude_none=True, mode="json"), elements)

    def buscar_por_paciente(self, uuid_paciente: str) -> list[dict]:
        paciente = self.paciente_repo.find_by_uuid(uuid_paciente)
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        doencas = self.repo.find_por_paciente(paciente.id)
        return [
            doenca_to_fhir_condition(d).model_dump(exclude_none=True, mode="json")
            for d in doencas
        ]

    def criar_a_partir_de_fhir(self, condition) -> dict:
        """POST /fhir/Condition -- INBOUND."""
        from src.models.pacientes import DoencaCronica
        from datetime import datetime

        try:
            dados = fhir_condition_to_dados(condition)
        except ValueError as e:
            raise DadosInvalidosError(str(e)) from e

        paciente = self.paciente_repo.find_by_uuid(dados["uuid_paciente"])
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {dados['uuid_paciente']}")

        doenca = DoencaCronica(
            id_paciente=paciente.id,
            codigo_cid10=dados["codigo_cid10"],
            descricao_cid10=dados["descricao_cid10"],
            desde=datetime.strptime(dados["desde"], "%Y-%m-%d").date(),
            status=dados["status"],
            observacoes=dados["observacoes"],
        )
        self.repo.save(doenca)
        recurso = doenca_to_fhir_condition(doenca)
        return recurso.model_dump(exclude_none=True, mode="json")
