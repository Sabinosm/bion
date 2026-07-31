"""Helpers compartilhados entre os services FHIR."""


def aplicar_elements(recurso: dict, elements: list[str] | None) -> dict:
    """Implementa o parâmetro _elements do FHIR (?_elements=name,telecom)."""
    if not elements:
        return recurso
    campos_preservados = {"resourceType", "id"}
    return {k: v for k, v in recurso.items() if k in campos_preservados or k in elements}
