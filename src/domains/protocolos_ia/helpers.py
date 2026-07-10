"""Funções utilitárias compartilhadas pelos domínios Protocolo e IA."""

from datetime import datetime, date

from src.core.exceptions import DadosInvalidosError


def parse_data(valor):
    """
    Converte uma string 'YYYY-MM-DD' em objeto date. Aceita também um
    date já pronto ou None, retornando-os sem alteração.

    Raises:
        DadosInvalidosError: se o valor não estiver no formato esperado.
    """
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")
