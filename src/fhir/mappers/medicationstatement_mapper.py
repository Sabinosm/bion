"""
Mapper MedicationStatement: traduz MedicamentoEmUso para/do Resource
MedicationStatement do FHIR (br-core-medicationstatement).

DECISÃO DE POLÍTICA (resolve a pendência levantada no planejamento):
o FHIR aceita tanto `medicationReference` (aponta para um Resource
Medication existente) quanto `medicationCodeableConcept` (texto livre
codificado, sem referência). Usamos isso a nosso favor:

- Se o medicamento informado bate com algo em catalogo_medicamentos
  (por nome), usamos id_catalogo normalmente.
- Se NÃO bate, não rejeitamos nem criamos entrada automática no
  catálogo -- extraímos texto2 sem entrada -> id_catalogo fica None,
  a stripe de medicação em uso simplesmente registra por descrição
  livre (dose, frequência, texto), o que já é suportado nativamente
  (MedicamentoEmUso.id_catalogo é nullable, MedicamentoEmUso.descricao existe).
"""

from fhir.resources.R4B.medicationstatement import MedicationStatement
from fhir.resources.R4B.reference import Reference
from fhir.resources.R4B.codeableconcept import CodeableConcept

STATUS_INTERNO_PARA_FHIR = {"ativo": "active", "interrompido": "stopped", "concluido": "completed"}
STATUS_FHIR_PARA_INTERNO = {v: k for k, v in STATUS_INTERNO_PARA_FHIR.items()}


def medicamento_to_fhir_medication_statement(medicamento) -> MedicationStatement:
    """OUTBOUND: MedicamentoEmUso -> MedicationStatement FHIR."""
    if medicamento.catalogo_medicamentos:
        medication_field = {
            "medicationReference": Reference(
                reference=f"Medication/{medicamento.catalogo_medicamentos.uuid}"
            )
        }
    else:
        # Sem catálogo vinculado: usa a descrição livre como
        # medicationCodeableConcept.text -- não força referência que
        # não existe.
        medication_field = {
            "medicationCodeableConcept": CodeableConcept(text=medicamento.descricao or "Medicamento não catalogado")
        }

    status_interno = medicamento.status_uso or ("ativo" if medicamento.flag_em_uso else "interrompido")

    return MedicationStatement(
        id=medicamento.uuid,
        status=STATUS_INTERNO_PARA_FHIR.get(status_interno, "active"),
        subject=Reference(reference=f"Patient/{medicamento.paciente.uuid}"),
        dosage=[{
            "text": " ".join(filter(None, [medicamento.dose, medicamento.frequencia])) or None,
        }] if (medicamento.dose or medicamento.frequencia) else [],
        effectivePeriod={"start": medicamento.desde.isoformat()} if medicamento.desde else None,
        **medication_field,
    )


def fhir_medication_statement_to_dados(ms: MedicationStatement, buscar_catalogo_por_nome) -> dict:
    """INBOUND: MedicationStatement FHIR -> dict pronto para
    DadosClinicosService.adicionar_medicamento_em_uso().

    Parâmetros:
        ms: instância validada de MedicationStatement.
        buscar_catalogo_por_nome: callable(nome: str) -> objeto do
            catálogo ou None. Injetado (não importado direto aqui) para
            manter o mapper sem dependência direta do repository --
            facilita testar o mapper isolado.

    Levanta:
        ValueError: se faltar subject.reference ou nenhuma forma de
            identificar o medicamento (nem reference nem codeable concept).
    """
    if not ms.subject or not ms.subject.reference:
        raise ValueError("MedicationStatement.subject.reference é obrigatório.")
    uuid_paciente = ms.subject.reference.split("/")[-1]

    id_catalogo = None
    descricao = None

    if getattr(ms, "medicationReference", None):
        # Referência explícita a um Medication já cadastrado -- resolve
        # pelo uuid embutido na reference (formato "Medication/{uuid}")
        uuid_medicamento = ms.medicationReference.reference.split("/")[-1]
        catalogo = buscar_catalogo_por_nome(uuid_medicamento, por_uuid=True)
        if not catalogo:
            raise ValueError(
                f"MedicationStatement.medicationReference aponta para "
                f"'{ms.medicationReference.reference}', que não existe no catálogo interno."
            )
        id_catalogo = catalogo.id
        descricao = catalogo.principio_ativo
    elif getattr(ms, "medicationCodeableConcept", None):
        nome = ms.medicationCodeableConcept.text
        if not nome and ms.medicationCodeableConcept.coding:
            nome = ms.medicationCodeableConcept.coding[0].display
        if not nome:
            raise ValueError("medicationCodeableConcept precisa ter 'text' ou coding.display.")

        descricao = nome
        # Tenta casar com o catálogo por nome (busca leve, não obrigatória
        # -- ver decisão de política no docstring do módulo). Se não achar,
        # segue sem catálogo, como texto livre.
        catalogo = buscar_catalogo_por_nome(nome, por_uuid=False)
        if catalogo:
            id_catalogo = catalogo.id
    else:
        raise ValueError(
            "MedicationStatement precisa de medicationReference ou "
            "medicationCodeableConcept."
        )

    status_fhir = ms.status or "active"
    status_uso = STATUS_FHIR_PARA_INTERNO.get(status_fhir, "ativo")

    dose = frequencia = None
    if ms.dosage:
        # Split simplificado do texto livre -- se o remetente já manda
        # dosage.text combinado, guardamos tudo em 'dose' e deixamos
        # 'frequencia' vazio, em vez de tentar parsear texto livre de
        # forma arriscada.
        dose = ms.dosage[0].text

    desde = None
    if ms.effectivePeriod and ms.effectivePeriod.start:
        desde = ms.effectivePeriod.start.isoformat() if hasattr(ms.effectivePeriod.start, "isoformat") else str(ms.effectivePeriod.start)

    return {
        "uuid_paciente": uuid_paciente,
        "id_catalogo": id_catalogo,
        "descricao": descricao,
        "dose": dose,
        "frequencia": frequencia,
        "desde": desde,
        "status_uso": status_uso,
        "flag_em_uso": status_uso == "ativo",
    }
