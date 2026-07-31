"""Service de orquestração FHIR para Observation (sinais vitais)."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ._helpers import aplicar_elements
from ..mappers.observation_mapper import sinal_vital_to_fhir_observation, fhir_observation_to_dados

# Conversão UCUM -> enum interno de unidade (SinalVital.unidade).
# Construída a partir dos códigos já confirmados em loinc_sinal_vital
# (05_sinal_vital_migration.sql) -- grafias diferentes do mesmo conceito.
UCUM_PARA_UNIDADE_INTERNA = {
    "/min": None,  # ambíguo: tanto FC quanto FR usam '/min' em UCUM,
                    # mas têm unidades internas diferentes (bpm vs irpm)
                    # -- resolvido por tipo_parametro, não por UCUM sozinho
    "%": "%",
    "mm[Hg]": "mmHg",
    "Cel": "°C",
    "mg/dL": "mg-dL",
}

UNIDADE_INTERNA_POR_TIPO_PARAMETRO = {
    "frequencia-cardiaca": "bpm",
    "frequencia-respiratoria": "irpm",
    "spo2": "%",
    "temperatura": "°C",
    "pa-sistolica": "mmHg",
    "pa-diastolica": "mmHg",
    "glicemia-capilar": "mg-dL",
}


class ObservationFhirService:
    def __init__(self):
        from src.domains.dados_clinicos.repository import SinalVitalRepository
        self.repo = SinalVitalRepository()

    def buscar_por_id(self, id_fhir: str, elements: list[str] | None = None) -> dict:
        sinal = self.repo.find_by_uuid(id_fhir)
        if not sinal:
            raise RecursoNaoEncontradoError(f"Observation não encontrada: {id_fhir}")
        recurso = sinal_vital_to_fhir_observation(sinal)
        return aplicar_elements(recurso.model_dump(exclude_none=True, mode="json"), elements)

    def buscar_por_atendimento(self, uuid_atendimento: str) -> list[dict]:
        from src.domains.atendimento.repository import AtendimentoRepository

        atendimento = AtendimentoRepository().find_by_uuid(uuid_atendimento)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        sinais = self.repo.find_por_atendimento(atendimento.id)
        return [
            sinal_vital_to_fhir_observation(s).model_dump(exclude_none=True, mode="json")
            for s in sinais
        ]

    def _resolver_loinc(self, codigo_loinc: str):
        """Callable injetado no mapper: código LOINC -> tipo_parametro interno."""
        from src.models.clinico import LoincSinalVital
        entrada = LoincSinalVital.query.filter_by(codigo_loinc=codigo_loinc).first()
        return entrada.tipo_parametro if entrada else None

    def criar_a_partir_de_fhir(self, obs, id_usuario: int) -> dict:
        """POST /fhir/Observation -- INBOUND.

        Exige que o Encounter (Atendimento) referenciado já exista --
        não cria atendimento "fantasma" a partir de um sinal vital
        isolado (ver ValueError no mapper).

        A UNIDADE (unidade interna de exibição) e a validação de faixa
        (flag_validacao_faixa) são resolvidas pelo service que já existe
        (DadosClinicosService.registrar_sinais_vitais), reaproveitado
        aqui para não duplicar essa lógica de negócio.
        """
        from src.domains.atendimento.repository import AtendimentoRepository
        from src.domains.dados_clinicos.service import DadosClinicosService

        try:
            dados = fhir_observation_to_dados(obs, self._resolver_loinc)
        except ValueError as e:
            raise DadosInvalidosError(str(e)) from e

        atendimento = AtendimentoRepository().find_by_uuid(dados["uuid_atendimento"])
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {dados['uuid_atendimento']}")

        # Resolve a unidade interna (enum de exibição) a partir do
        # tipo_parametro -- mais confiável do que tentar converter o
        # UCUM diretamente, já que '/min' sozinho é ambíguo entre FC e FR.
        unidade_interna = UNIDADE_INTERNA_POR_TIPO_PARAMETRO.get(dados["tipo_parametro"])
        if not unidade_interna:
            raise DadosInvalidosError(
                f"Não foi possível resolver a unidade interna para "
                f"tipo_parametro='{dados['tipo_parametro']}'."
            )

        # Reaproveita o service de domínio já existente (que já faz a
        # validação de tipo_parametro, cria o registro etc) em vez de
        # duplicar a lógica de criação aqui.
        clinico_svc = DadosClinicosService()
        registrados = clinico_svc.registrar_sinais_vitais(
            dados["uuid_atendimento"],
            [{
                "tipo_parametro": dados["tipo_parametro"],
                "valor_numerico": dados["valor_numerico"],
                "unidade": unidade_interna,
            }],
            id_usuario,
        )
        sinal = registrados[0]
        recurso = sinal_vital_to_fhir_observation(sinal)
        return recurso.model_dump(exclude_none=True, mode="json")
