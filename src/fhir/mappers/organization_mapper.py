"""
Mapper Organization: traduz Empresa (+ EmpresaIdentificador) para o
Resource Organization do FHIR (br-core-organization). Só OUTBOUND.
"""


def empresa_to_fhir_organization(empresa) -> dict:
    """OUTBOUND: Empresa -> Organization FHIR (br-core-organization).

    NOTA (ver REFERENCIA_FHIR.md): systems de CNPJ/CNES ainda são
    pendentes de confirmação nacional -- usando URL provisória até
    validar contra a terminologia oficial br-core.
    """
    identifiers = []
    for ident in empresa.identificadores:
        # PENDENTE: confirmar NamingSystem nacional oficial (só achamos
        # referência estadual SES-GO até agora)
        system = f"https://saude.gov.br/fhir/sid/{ident.tipo_identificador}"
        identifiers.append({
            "type": {"text": ident.tipo_identificador.upper()},
            "system": system,
            "value": ident.valor,
        })

    return {
        "resourceType": "Organization",
        "id": empresa.uuid,
        "identifier": identifiers,
        "active": empresa.status_plano not in ("cancelado", "suspenso"),
        "name": empresa.nome_fantasia,
        "alias": [empresa.razao_social] if empresa.razao_social else [],
    }
