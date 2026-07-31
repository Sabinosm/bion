"""
Mapper AllergyIntolerance: traduz Alergia (+ ReacaoAlergia[]) para/do
Resource AllergyIntolerance do FHIR (br-core-allergyintolerance).

ACHADO IMPORTANTE testando com fhir.resources: reaction.severity usa
os valores em INGLÊS do FHIR base (mild/moderate/severe), não o enum
em português que usamos internamente (leve/moderada/grave). O schema
manual anterior tinha esse detalhe errado -- confirmado agora contra
a biblioteca oficial.
"""

from fhir.resources.R4B.allergyintolerance import AllergyIntolerance
from fhir.resources.R4B.reference import Reference
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding

SEVERITY_INTERNO_PARA_FHIR = {"leve": "mild", "moderada": "moderate", "grave": "severe"}
SEVERITY_FHIR_PARA_INTERNO = {v: k for k, v in SEVERITY_INTERNO_PARA_FHIR.items()}


def alergia_to_fhir_allergy_intolerance(alergia) -> AllergyIntolerance:
    """OUTBOUND: Alergia -> AllergyIntolerance FHIR."""
    codigo_coding = []
    if alergia.codigo_substancia:
        codigo_coding.append(Coding(
            system=alergia.sistema_codigo_substancia or "http://snomed.info/sct",
            code=alergia.codigo_substancia,
            display=alergia.substancia,
        ))

    return AllergyIntolerance(
        id=alergia.uuid,
        clinicalStatus=CodeableConcept(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
            code="active",
        )]),
        verificationStatus=CodeableConcept(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
            code="confirmed" if alergia.flag_confirmado else "unconfirmed",
        )]),
        code=CodeableConcept(coding=codigo_coding, text=alergia.substancia),
        patient=Reference(reference=f"Patient/{alergia.paciente.uuid}"),
        reaction=[
            {
                "manifestation": [{"text": r.manifestacao}],
                "description": r.descricao,
                "onset": r.data_ocorrencia.isoformat() if r.data_ocorrencia else None,
                "severity": SEVERITY_INTERNO_PARA_FHIR.get(r.gravidade, r.gravidade),
            }
            for r in alergia.reacoes
        ],
    )


def fhir_allergy_intolerance_to_dados(allergy: AllergyIntolerance) -> dict:
    """INBOUND: AllergyIntolerance FHIR -> dict pronto para
    DadosClinicosService.adicionar_alergia().

    Retorno:
        dict com: uuid_paciente (extraído da reference), substancia,
        codigo_substancia, flag_confirmado, e a lista de reações já
        traduzida (severity de volta para português).

    Levanta:
        ValueError: se faltar patient.reference ou reaction.
    """
    if not allergy.patient or not allergy.patient.reference:
        raise ValueError("AllergyIntolerance.patient.reference é obrigatório.")

    uuid_paciente = allergy.patient.reference.split("/")[-1]

    codigo_substancia = None
    sistema_codigo = None
    if allergy.code and allergy.code.coding:
        codigo_substancia = allergy.code.coding[0].code
        sistema_codigo = allergy.code.coding[0].system

    substancia = None
    if allergy.code:
        substancia = allergy.code.text or (
            allergy.code.coding[0].display if allergy.code.coding else None
        )
    if not substancia:
        raise ValueError("AllergyIntolerance.code precisa ter 'text' ou coding[0].display.")

    flag_confirmado = False
    if allergy.verificationStatus and allergy.verificationStatus.coding:
        flag_confirmado = allergy.verificationStatus.coding[0].code == "confirmed"

    if not allergy.reaction:
        raise ValueError("AllergyIntolerance precisa de ao menos uma reaction.")

    reacoes = []
    for r in allergy.reaction:
        manifestacao = None
        if r.manifestation:
            manifestacao = r.manifestation[0].text
        if not manifestacao:
            raise ValueError("reaction.manifestation[0].text é obrigatório.")

        gravidade_fhir = r.severity or "moderate"
        reacoes.append({
            "manifestacao": manifestacao,
            "gravidade": SEVERITY_FHIR_PARA_INTERNO.get(gravidade_fhir, "moderada"),
            "descricao": r.description,
            "data_ocorrencia": r.onset.isoformat() if getattr(r, "onset", None) else None,
        })

    return {
        "uuid_paciente": uuid_paciente,
        "substancia": substancia,
        "codigo_substancia": codigo_substancia,
        "sistema_codigo_substancia": sistema_codigo,
        "flag_confirmado": flag_confirmado,
        "reacoes": reacoes,
    }
