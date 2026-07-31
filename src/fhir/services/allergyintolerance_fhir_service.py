"""
Service de orquestração FHIR para AllergyIntolerance -- outbound (já
existia) + NOVO inbound.
"""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ._helpers import aplicar_elements
from ..mappers.allergyintolerance_mapper import (
    alergia_to_fhir_allergy_intolerance,
    fhir_allergy_intolerance_to_dados,
)


class AllergyIntoleranceFhirService:
    def __init__(self):
        from src.domains.paciente.repositories import AlergiaRepository, PacienteRepository
        self.repo = AlergiaRepository()
        self.paciente_repo = PacienteRepository()

    def buscar_por_id(self, id_fhir: str, elements: list[str] | None = None) -> dict:
        alergia = self.repo.find_by_uuid(id_fhir)
        if not alergia:
            raise RecursoNaoEncontradoError(f"AllergyIntolerance não encontrada: {id_fhir}")
        recurso = alergia_to_fhir_allergy_intolerance(alergia)
        return aplicar_elements(recurso.model_dump(exclude_none=True, mode="json"), elements)

    def buscar_por_paciente(self, uuid_paciente: str) -> list[dict]:
        paciente = self.paciente_repo.find_by_uuid(uuid_paciente)
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        alergias = self.repo.find_por_paciente(paciente.id)
        return [
            alergia_to_fhir_allergy_intolerance(a).model_dump(exclude_none=True, mode="json")
            for a in alergias
        ]

    def criar_a_partir_de_fhir(self, allergy) -> dict:
        """POST /fhir/AllergyIntolerance -- caminho INBOUND (novo).

        Diferente de DadosClinicosService.adicionar_alergia() (que cria
        só UMA reação junto com a alergia), este método aceita o
        histórico COMPLETO de reações que pode vir num recurso FHIR
        externo (ex: paciente transferido de outro sistema).

        Parâmetros:
            allergy: instância de fhir.resources.R4B.allergyintolerance.AllergyIntolerance,
                já validada estruturalmente pela rota.

        Levanta:
            RecursoNaoEncontradoError: se o paciente referenciado não existir.
            DadosInvalidosError: se faltar dado obrigatório (propagado
                do ValueError do mapper).
        """
        from src.models.pacientes import Alergia

        try:
            dados = fhir_allergy_intolerance_to_dados(allergy)
        except ValueError as e:
            raise DadosInvalidosError(str(e)) from e

        paciente = self.paciente_repo.find_by_uuid(dados["uuid_paciente"])
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {dados['uuid_paciente']}")

        alergia = Alergia(
            id_paciente=paciente.id,
            substancia=dados["substancia"],
            codigo_substancia=dados["codigo_substancia"],
            sistema_codigo_substancia=dados["sistema_codigo_substancia"],
            flag_confirmado=dados["flag_confirmado"],
        )
        for r in dados["reacoes"]:
            alergia.registrar_reacao(
                manifestacao=r["manifestacao"],
                gravidade=r["gravidade"],
                descricao=r["descricao"],
                data_ocorrencia=r["data_ocorrencia"],
            )

        self.repo.save(alergia)
        recurso = alergia_to_fhir_allergy_intolerance(alergia)
        return recurso.model_dump(exclude_none=True, mode="json")
