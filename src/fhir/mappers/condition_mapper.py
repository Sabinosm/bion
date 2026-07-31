"""
Mapper Condition: traduz DoencaCronica para/do Resource Condition do
FHIR (BRCoreCondition).

ACHADO IMPORTANTE testando com fhir.resources: Condition usa `subject`
para referenciar o paciente, NÃO `patient` (diferente de
AllergyIntolerance, que usa `patient`). Detalhe fácil de errar sem
testar contra a lib real.
"""

from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.reference import Reference
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding

SYSTEM_CID10 = "http://hl7.org/fhir/sid/icd-10"

STATUS_INTERNO_PARA_FHIR = {"ativa": "active", "em-remissao": "remission"}
STATUS_FHIR_PARA_INTERNO = {v: k for k, v in STATUS_INTERNO_PARA_FHIR.items()}


def doenca_to_fhir_condition(doenca) -> Condition:
    """OUTBOUND: DoencaCronica -> Condition FHIR."""
    return Condition(
        id=doenca.uuid,
        clinicalStatus=CodeableConcept(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/condition-clinical",
            code=STATUS_INTERNO_PARA_FHIR.get(doenca.status, "active"),
        )]),
        code=CodeableConcept(
            coding=[Coding(system=SYSTEM_CID10, code=doenca.codigo_cid10, display=doenca.descricao_cid10)],
            text=doenca.descricao_cid10,
        ),
        subject=Reference(reference=f"Patient/{doenca.paciente.uuid}"),
        onsetDateTime=doenca.desde.isoformat() if doenca.desde else None,
        note=[{"text": doenca.observacoes}] if doenca.observacoes else [],
    )


def fhir_condition_to_dados(condition: Condition) -> dict:
    """INBOUND: Condition FHIR -> dict pronto para
    DadosClinicosService.adicionar_doenca().

    Levanta:
        ValueError: se faltar subject.reference, code, ou os campos
            CID-10 necessários.
    """
    if not condition.subject or not condition.subject.reference:
        raise ValueError("Condition.subject.reference é obrigatório.")
    uuid_paciente = condition.subject.reference.split("/")[-1]

    if not condition.code or not condition.code.coding:
        raise ValueError(
            "Condition.code.coding é obrigatório (esperado ao menos um "
            f"coding com system={SYSTEM_CID10})."
        )

    coding_cid10 = next(
        (c for c in condition.code.coding if c.system == SYSTEM_CID10),
        condition.code.coding[0],  # fallback: usa o primeiro se nenhum bater o system esperado
    )

    descricao = condition.code.text or coding_cid10.display
    if not descricao:
        raise ValueError("Condition.code precisa ter 'text' ou coding.display.")

    status = "ativa"
    if condition.clinicalStatus and condition.clinicalStatus.coding:
        status_fhir = condition.clinicalStatus.coding[0].code
        status = STATUS_FHIR_PARA_INTERNO.get(status_fhir, "ativa")

    desde = None
    # onsetDateTime pode vir em diferentes formas (onset[x]) -- tratamos
    # só o caso mais comum aqui; onsetPeriod/onsetString ficam para
    # quando surgir necessidade real.
    if getattr(condition, "onsetDateTime", None):
        desde = condition.onsetDateTime.isoformat() if hasattr(condition.onsetDateTime, "isoformat") else str(condition.onsetDateTime)

    if not desde:
        raise ValueError(
            "Condition.onsetDateTime é obrigatório (campo 'desde' é "
            "NOT NULL no domínio interno)."
        )

    observacoes = None
    if condition.note:
        observacoes = condition.note[0].text

    return {
        "uuid_paciente": uuid_paciente,
        "codigo_cid10": coding_cid10.code,
        "descricao_cid10": descricao,
        "desde": desde,
        "status": status,
        "observacoes": observacoes,
    }
