"""
Mapper Practitioner: traduz entre Usuario/PapelProfissional (domínio) e
o Resource Practitioner do FHIR (br-core-practitioner).

REESCRITO para usar fhir.resources.R4B: a construção do recurso agora
passa pelas classes Pydantic oficiais da biblioteca (geradas a partir
da StructureDefinition real), em vez de dicts montados à mão -- reduz
o risco de esquecer um campo obrigatório ou errar cardinalidade.

R4B foi escolhido (não R5, que é o default da lib) porque br-core é
baseado em R4, e a biblioteca confirma que R4B mantém compatibilidade
com recursos R4 (as diferenças entre as duas versões são pequenas).
"""

from fhir.resources.R4B.practitioner import Practitioner
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.humanname import HumanName
from fhir.resources.R4B.contactpoint import ContactPoint

from src.core.security import aes_decrypt

# Confirmado na spec oficial (hl7.org.br/fhir/core/StructureDefinition-br-core-practitioner.html)
SYSTEM_CPF = "https://saude.gov.br/fhir/sid/cpf"
CODE_SYSTEM_TIPO_DOCUMENTO = "http://terminology.hl7.org/CodeSystem/v2-0203"

# ValueSets de vínculo (binding required) -- não são o `system` final,
# são o conjunto de valores válidos (ver nota em _resolver_system_conselho).
VALUESET_BRCRM = "https://terminologia.saude.gov.br/fhir/ValueSet/BRCRM"
VALUESET_BRCOREN = "https://terminologia.saude.gov.br/fhir/ValueSet/BRCOREN"


def _resolver_system_conselho(tipo_papel: str, uf_conselho: str) -> str:
    """PENDENTE DE CONFIRMAÇÃO (ver REFERENCIA_FHIR.md): a spec br-core
    vincula isso a um ValueSet (BRCRM/BRCOREN), não expõe uma URL única
    fixa por conselho regional. Convenção provisória até validar contra
    a terminologia oficial."""
    prefixo = "crm" if tipo_papel == "medico" else "coren"
    return f"https://terminologia.saude.gov.br/fhir/NamingSystem/{prefixo}-{uf_conselho.lower()}"


def usuario_papel_to_fhir_practitioner(usuario, papel=None) -> Practitioner:
    """OUTBOUND: Usuario (+ PapelProfissional opcional) -> Practitioner FHIR.

    Retorna a INSTÂNCIA da classe Practitioner (não um dict) -- quem
    chamar decide se serializa com .model_dump() ou .model_dump_json().
    """
    identifiers = [
        Identifier(
            use="official",
            type=CodeableConcept(coding=[Coding(system=CODE_SYSTEM_TIPO_DOCUMENTO, code="TAX")]),
            system=SYSTEM_CPF,
            value=aes_decrypt(usuario.cpf),
        )
    ]

    if papel is not None:
        code = "MD" if papel.tipo_papel == "medico" else "RN"
        identifiers.append(
            Identifier(
                use="official",
                type=CodeableConcept(coding=[Coding(system=CODE_SYSTEM_TIPO_DOCUMENTO, code=code)]),
                system=_resolver_system_conselho(papel.tipo_papel, papel.uf_conselho),
                value=papel.numero_conselho,
            )
        )

    telecom = []
    if usuario.email:
        telecom.append(ContactPoint(system="email", value=usuario.email))
    if usuario.telefone:
        telecom.append(ContactPoint(system="phone", value=usuario.telefone))

    return Practitioner(
        id=usuario.uuid,
        identifier=identifiers,
        active=(usuario.status == "ativo"),
        name=[HumanName(use="official", text=usuario.nome_completo)],
        telecom=telecom,
    )


def fhir_practitioner_to_dados_cadastro(practitioner: Practitioner) -> dict:
    """INBOUND: Practitioner FHIR (já validado pela classe da lib) ->
    dict pronto para CadastroUsuarioSchema.

    Parâmetros:
        practitioner: instância de fhir.resources.R4B.practitioner.Practitioner,
            já construída (e portanto já validada estruturalmente) a
            partir do JSON recebido.

    Retorno:
        dict com chaves no formato que CadastroUsuarioSchema espera.
    """
    cpf = None
    for ident in (practitioner.identifier or []):
        if ident.system == SYSTEM_CPF:
            cpf = ident.value
            break

    if not cpf:
        raise ValueError(
            "Practitioner recebido não contém identifier de CPF "
            f"(system esperado: {SYSTEM_CPF})."
        )

    nome_completo = None
    if practitioner.name:
        primeiro = practitioner.name[0]
        nome_completo = primeiro.text or " ".join(
            (primeiro.given or []) + ([primeiro.family] if primeiro.family else [])
        ).strip()

    email = telefone = None
    for t in (practitioner.telecom or []):
        if t.system == "email":
            email = t.value
        elif t.system == "phone":
            telefone = t.value

    return {
        "nome_completo": nome_completo,
        "cpf": cpf,
        "email": email,
        "telefone": telefone,
    }
