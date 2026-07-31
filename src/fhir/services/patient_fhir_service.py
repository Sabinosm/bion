"""Service de orquestração FHIR para Patient."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ._helpers import aplicar_elements
from ..mappers.patient_mapper import paciente_to_fhir_patient, fhir_patient_to_dados_cadastro


class PatientFhirService:
    def __init__(self):
        from src.domains.paciente.repositories import PacienteRepository
        self.repo = PacienteRepository()

    def buscar_por_id(self, id_fhir: str, elements: list[str] | None = None) -> dict:
        paciente = self.repo.find_by_uuid(id_fhir)
        if not paciente:
            raise RecursoNaoEncontradoError(f"Patient não encontrado: {id_fhir}")
        recurso = paciente_to_fhir_patient(paciente)
        return aplicar_elements(recurso.model_dump(exclude_none=True, mode="json"), elements)

    def criar_a_partir_de_fhir(
        self, patient, id_usuario_cadastro: int,
        consentimento_versao: str, consentimento_canal: str,
    ) -> dict:
        """POST /fhir/Patient -- INBOUND (novo).

        Orquestra DUAS chamadas de service já existentes:
          1. PacienteService.cadastrar() -- cria Paciente + PacienteDadosPessoais
          2. ConsentimentoService.registrar() -- cria o Consentimento LGPD

        Parâmetros:
            patient: instância validada de fhir.resources.R4B.patient.Patient.
            id_usuario_cadastro: quem está registrando (da sessão, não do FHIR).
            consentimento_versao: OBRIGATÓRIO, não vem no Patient FHIR
                (decisão de política, ver README_RECEBIMENTO.md).
            consentimento_canal: idem.

        Levanta:
            DadosInvalidosError: se faltar dado obrigatório no Patient
                (propagado do mapper) ou no consentimento.
            ConflictoError: se já existir paciente com esse CPF
                (propagado de PacienteService.cadastrar).
        """
        from src.domains.paciente.services import PacienteService, ConsentimentoService

        if not consentimento_versao or not consentimento_canal:
            raise DadosInvalidosError(
                "consentimento_versao e consentimento_canal são obrigatórios -- "
                "não fazem parte do Resource Patient padrão (ver README_RECEBIMENTO.md)."
            )

        try:
            dados = fhir_patient_to_dados_cadastro(patient)
        except ValueError as e:
            raise DadosInvalidosError(str(e)) from e

        paciente_svc = PacienteService()
        # PacienteService.cadastrar() já faz toda a validação de negócio
        # que precisamos (duplicidade de CPF, campos obrigatórios) --
        # não duplicamos essa lógica aqui.
        paciente = paciente_svc.cadastrar(dados, id_usuario_cadastro)

        consentimento_svc = ConsentimentoService()
        consentimento_svc.registrar(
            paciente.uuid,
            {"versao_termo": consentimento_versao, "canal_coleta": consentimento_canal},
            id_usuario_cadastro,
        )

        recurso = paciente_to_fhir_patient(paciente)
        return recurso.model_dump(exclude_none=True, mode="json")
