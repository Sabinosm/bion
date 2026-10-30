"""comum_protocolo_composto.py

Utilitários compartilhados pelos avaliadores das famílias do protocolo
composto. Hoje concentra a construção do resultado de um módulo que não pôde
ser calculado, padrão repetido por todas as famílias.
"""
from ..schemas.protocolo_composto_schemas import ModuloDef, ResultadoModulo


def resultado_nao_calculavel(modulo: ModuloDef, ausentes: list[str], motivo: str) -> ResultadoModulo:
    """Resultado de um módulo que não pôde ser calculado, com os dados ausentes e o motivo."""
    return ResultadoModulo(
        sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
        tipo_saida=modulo.tipo_saida, ausentes=ausentes, motivo=motivo,
    )
