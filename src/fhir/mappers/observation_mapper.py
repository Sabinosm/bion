"""
Mapper Observation (vital signs): traduz SinalVital para/do Resource
Observation do FHIR.

Confirmado: Observation usa subject (paciente) E encounter (atendimento)
como referências separadas -- diferente de AllergyIntolerance/Condition/
MedicationStatement, que só referenciam o paciente diretamente.
"""

from fhir.resources.R4B.observation import Observation
from fhir.resources.R4B.reference import Reference
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.quantity import Quantity


def sinal_vital_to_fhir_observation(sinal_vital) -> Observation:
    """OUTBOUND: SinalVital -> Observation FHIR (vital-signs)."""
    loinc = sinal_vital.loinc_ref
    return Observation(
        id=sinal_vital.uuid,
        status="final",
        category=[CodeableConcept(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/observation-category",
            code="vital-signs",
        )])],
        code=CodeableConcept(coding=[Coding(
            system="http://loinc.org", code=loinc.codigo_loinc, display=loinc.display_loinc,
        )]),
        subject=Reference(reference=f"Patient/{sinal_vital.atendimento.consulta.paciente.uuid}"),
        encounter=Reference(reference=f"Encounter/{sinal_vital.atendimento.uuid}"),
        valueQuantity=Quantity(
            value=float(sinal_vital.valor_numerico),
            unit=loinc.unidade_ucum,
            system="http://unitsofmeasure.org",
            code=loinc.unidade_ucum,
        ),
        effectiveDateTime=sinal_vital.data_hora_medicao.isoformat() if sinal_vital.data_hora_medicao else None,
        performer=[Reference(reference=f"Practitioner/{sinal_vital.usuario.uuid}")],
    )


def fhir_observation_to_dados(obs: Observation, resolver_loinc) -> dict:
    """INBOUND: Observation FHIR -> dict pronto para
    DadosClinicosService.registrar_sinais_vitais() (adaptado para 1 item).

    Parâmetros:
        obs: instância validada de Observation.
        resolver_loinc: callable(codigo_loinc: str) -> tipo_parametro
            interno (ou None se não reconhecido). Injetado para não
            acoplar o mapper direto ao banco.

    Levanta:
        ValueError: se faltar encounter.reference, code, ou
            valueQuantity, ou se o código LOINC não for reconhecido
            na nossa tabela de referência.
    """
    if not obs.encounter or not obs.encounter.reference:
        raise ValueError(
            "Observation.encounter.reference é obrigatório -- não criamos "
            "um Atendimento novo a partir de um sinal vital isolado, o "
            "Atendimento precisa já existir no sistema."
        )
    uuid_atendimento = obs.encounter.reference.split("/")[-1]

    if not obs.code or not obs.code.coding:
        raise ValueError("Observation.code.coding é obrigatório.")
    codigo_loinc = obs.code.coding[0].code

    tipo_parametro = resolver_loinc(codigo_loinc)
    if not tipo_parametro:
        raise ValueError(
            f"Código LOINC '{codigo_loinc}' não reconhecido na tabela de "
            "referência interna (loinc_sinal_vital)."
        )

    if not obs.valueQuantity or obs.valueQuantity.value is None:
        raise ValueError("Observation.valueQuantity.value é obrigatório.")

    return {
        "uuid_atendimento": uuid_atendimento,
        "tipo_parametro": tipo_parametro,
        "valor_numerico": float(obs.valueQuantity.value),
        # unidade interna (mmHg, bpm etc) é resolvida pelo service a
        # partir do tipo_parametro -- não confiamos no unit que veio de
        # fora para essa coluna de exibição, para manter consistência
        # com a tabela loinc_sinal_vital.
    }
