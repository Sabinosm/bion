"""Service de orquestração FHIR para MedicationStatement."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ._helpers import aplicar_elements
from ..mappers.medicationstatement_mapper import (
    medicamento_to_fhir_medication_statement,
    fhir_medication_statement_to_dados,
)


class MedicationStatementFhirService:
    def __init__(self):
        from src.domains.paciente.repositories import MedicamentoEmUsoRepository, PacienteRepository
        self.repo = MedicamentoEmUsoRepository()
        self.paciente_repo = PacienteRepository()

    def buscar_por_id(self, id_fhir: str, elements: list[str] | None = None) -> dict:
        med = self.repo.find_by_uuid(id_fhir)
        if not med:
            raise RecursoNaoEncontradoError(f"MedicationStatement não encontrado: {id_fhir}")
        recurso = medicamento_to_fhir_medication_statement(med)
        return aplicar_elements(recurso.model_dump(exclude_none=True, mode="json"), elements)

    def buscar_por_paciente(self, uuid_paciente: str) -> list[dict]:
        paciente = self.paciente_repo.find_by_uuid(uuid_paciente)
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        medicamentos = self.repo.find_por_paciente(paciente.id)
        return [
            medicamento_to_fhir_medication_statement(m).model_dump(exclude_none=True, mode="json")
            for m in medicamentos
        ]

    def _buscar_catalogo(self, valor: str, por_uuid: bool):
        """Callable injetado no mapper -- ver docstring em
        medicationstatement_mapper.py sobre por que essa indireção existe."""
        from src.models.clinico import CatalogoMedicamentos

        if por_uuid:
            return CatalogoMedicamentos.query.filter_by(uuid_catalogo_medicamentos=valor).first()
        # Busca por nome: aproximação simples (case-insensitive, contains).
        # Não é fuzzy matching de verdade -- se precisar de mais precisão
        # no futuro, considerar um índice de busca textual dedicado.
        return CatalogoMedicamentos.query.filter(
            CatalogoMedicamentos.principio_ativo.ilike(f"%{valor}%")
        ).first()

    def criar_a_partir_de_fhir(self, ms) -> dict:
        """POST /fhir/MedicationStatement -- INBOUND."""
        from src.models.pacientes import MedicamentoEmUso
        from datetime import datetime

        try:
            dados = fhir_medication_statement_to_dados(ms, self._buscar_catalogo)
        except ValueError as e:
            raise DadosInvalidosError(str(e)) from e

        paciente = self.paciente_repo.find_by_uuid(dados["uuid_paciente"])
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {dados['uuid_paciente']}")

        medicamento = MedicamentoEmUso(
            id_paciente=paciente.id,
            id_catalogo=dados["id_catalogo"],
            descricao=dados["descricao"],
            dose=dados["dose"],
            frequencia=dados["frequencia"],
            desde=datetime.strptime(dados["desde"], "%Y-%m-%d").date() if dados["desde"] else None,
            flag_em_uso=dados["flag_em_uso"],
            status_uso=dados["status_uso"],
        )
        self.repo.save(medicamento)
        recurso = medicamento_to_fhir_medication_statement(medicamento)
        return recurso.model_dump(exclude_none=True, mode="json")
