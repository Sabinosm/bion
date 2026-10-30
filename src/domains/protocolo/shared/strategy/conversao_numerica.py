"""conversao_numerica.py

Conversão padronizada de respostas numéricas vindas do front, compartilhada
por todas as famílias de protocolo para que "número válido" signifique a mesma
coisa em qualquer uma: aceita número ou texto com vírgula decimal e rejeita
booleano, NaN e infinito.
"""
import math


def converter_numero(campo: str, bruto) -> int | float:
    """Converte a resposta bruta em número (int se inteiro, senão float).

    Raises:
        ValueError: com a mensagem de erro do campo.
    """
    if isinstance(bruto, bool):
        raise ValueError(f"'{campo}': valor numérico inválido")
    try:
        numero = float(str(bruto).replace(",", ".")) if isinstance(bruto, str) else float(bruto)
    except ValueError:
        raise ValueError(f"'{campo}': '{bruto}' não é um número") from None
    if not math.isfinite(numero):
        raise ValueError(f"'{campo}': valor numérico inválido")
    return int(numero) if numero.is_integer() else numero
