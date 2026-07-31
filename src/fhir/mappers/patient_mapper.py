"""
Mapper Patient: traduz Paciente (+ PacienteDadosPessoais) para/do
Resource Patient do FHIR (br-core-patient).

REESCRITO outbound para fhir.resources.R4B (era dict manual antes).
INBOUND é NOVO -- decisão de política (Opção B do planejamento):
consentimento LGPD é exigido como parâmetro FORA do corpo FHIR
(mais pragmático que exigir um Consent Resource junto via Bundle).
"""

from fhir.resources.R4B.patient import Patient
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.humanname import HumanName
from fhir.resources.R4B.contactpoint import ContactPoint
from fhir.resources.R4B.patient import PatientContact

from src.core.security import aes_decrypt

SYSTEM_CPF = "https://saude.gov.br/fhir/sid/cpf"
CODE_SYSTEM_TIPO_DOCUMENTO = "http://terminology.hl7.org/CodeSystem/v2-0203"
MAPA_GENERO_INTERNO_PARA_FHIR = {"M": "male", "F": "female", "I": "other"}
MAPA_GENERO_FHIR_PARA_INTERNO = {v: k for k, v in MAPA_GENERO_INTERNO_PARA_FHIR.items()}


def paciente_to_fhir_patient(paciente) -> Patient:
    """OUTBOUND: Paciente -> Patient FHIR. Respeita direito ao
    esquecimento (ver lógica condicional abaixo)."""
    identifiers = []

    if paciente.esta_anonimizado():
        if paciente.identificacao_anonima:
            identifiers.append(Identifier(
                use="secondary",
                system="https://bion.com.br/fhir/sid/anonimizado",
                value=paciente.identificacao_anonima,
            ))
    else:
        identifiers.append(Identifier(
            use="official",
            type=CodeableConcept(coding=[Coding(system=CODE_SYSTEM_TIPO_DOCUMENTO, code="TAX")]),
            system=SYSTEM_CPF,
            value=aes_decrypt(paciente.pessoal.cpf) if paciente.pessoal.cpf else None,
        ))

    kwargs = {
        "id": paciente.uuid,
        "identifier": identifiers,
        "active": paciente.status == "ativo",
        "gender": MAPA_GENERO_INTERNO_PARA_FHIR.get(paciente.sexo_biologico),
        "birthDate": paciente.data_nascimento.isoformat() if paciente.data_nascimento else None,
    }

    if paciente.data_obito:
        kwargs["deceasedDateTime"] = paciente.data_obito.isoformat()
    else:
        kwargs["deceasedBoolean"] = paciente.falecido

    if not paciente.esta_anonimizado() and paciente.pessoal:
        kwargs["name"] = [HumanName(use="official", text=paciente.pessoal.nome_completo)]

        telecom = []
        if paciente.pessoal.telefone:
            telecom.append(ContactPoint(system="phone", value=aes_decrypt(paciente.pessoal.telefone)))
        if paciente.pessoal.email:
            telecom.append(ContactPoint(system="email", value=aes_decrypt(paciente.pessoal.email)))
        if telecom:
            kwargs["telecom"] = telecom

        if paciente.pessoal.contato_emergencia_nome:
            kwargs["contact"] = [PatientContact(
                relationship=[CodeableConcept(coding=[Coding(
                    system="http://terminology.hl7.org/CodeSystem/v2-0131",
                    code="C", display="Emergency Contact",
                )])],
                name=HumanName(text=paciente.pessoal.contato_emergencia_nome),
                telecom=(
                    [ContactPoint(system="phone", value=aes_decrypt(paciente.pessoal.contato_emergencia_telefone))]
                    if paciente.pessoal.contato_emergencia_telefone else []
                ),
            )]

    return Patient(**kwargs)


def fhir_patient_to_dados_cadastro(patient: Patient) -> dict:
    """INBOUND: Patient FHIR -> dict pronto para
    PacienteService.cadastrar() (que já existe e já faz toda a
    validação de negócio: duplicidade de CPF, campos obrigatórios etc).

    NOTA: consentimento LGPD, cadastrado_por e id_regiao_geografica
    NÃO vêm daqui -- são resolvidos pela rota (parâmetros extras /
    sessão logada), por decisão de política documentada em
    README_RECEBIMENTO.md.

    Levanta:
        ValueError: se faltar identifier de CPF ou name.
    """
    cpf = None
    for ident in (patient.identifier or []):
        if ident.system == SYSTEM_CPF:
            cpf = ident.value
            break
    if not cpf:
        raise ValueError(f"Patient recebido não contém identifier de CPF (system esperado: {SYSTEM_CPF}).")

    if not patient.name:
        raise ValueError("Patient.name é obrigatório para o cadastro interno.")
    primeiro_nome = patient.name[0]
    nome_completo = primeiro_nome.text or " ".join(
        (primeiro_nome.given or []) + ([primeiro_nome.family] if primeiro_nome.family else [])
    ).strip()
    if not nome_completo:
        raise ValueError("Não foi possível extrair nome_completo de Patient.name.")

    if not patient.gender:
        raise ValueError("Patient.gender é obrigatório (mapeado para sexo_biologico, NOT NULL no domínio).")
    sexo_biologico = MAPA_GENERO_FHIR_PARA_INTERNO.get(patient.gender, "I")

    if not patient.birthDate:
        raise ValueError("Patient.birthDate é obrigatório.")

    email = telefone = None
    for t in (patient.telecom or []):
        if t.system == "email":
            email = t.value
        elif t.system == "phone":
            telefone = t.value

    contato_emergencia_nome = contato_emergencia_telefone = None
    if patient.contact:
        primeiro_contato = patient.contact[0]
        if primeiro_contato.name:
            contato_emergencia_nome = primeiro_contato.name.text
        if primeiro_contato.telecom:
            for t in primeiro_contato.telecom:
                if t.system == "phone":
                    contato_emergencia_telefone = t.value

    return {
        "cpf": cpf,
        "nome_completo": nome_completo,
        "sexo_biologico": sexo_biologico,
        "data_nascimento": patient.birthDate.isoformat() if hasattr(patient.birthDate, "isoformat") else str(patient.birthDate),
        "email": email,
        "telefone": telefone,
        "contato_emergencia_nome": contato_emergencia_nome,
        "contato_emergencia_telefone": contato_emergencia_telefone,
    }
