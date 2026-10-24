"""filtros.py -- apoio compartilhado aos históricos de Consulta e Atendimento.

Valida os filtros recebidos pela query string (opções de enum e datas), converte o período
informado em datas locais da empresa para limites em UTC (como o banco guarda) e monta o
envelope de paginação com o indicador de "tem mais". Não acessa o banco.
"""

from datetime import date, datetime, time, timedelta, timezone

from src.core.exceptions import DadosInvalidosError


def validar_opcao(valor, validos, campo: str):
    """Devolve o valor se estiver em `validos`; vazio/None vira None; senão 422 apontando o campo."""
    if valor is None or valor == "":
        return None
    if valor not in validos:
        raise DadosInvalidosError({campo: "inválido; use um de: " + ", ".join(validos)})
    return valor


def _parse_data(valor, campo: str):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise DadosInvalidosError({campo: "use o formato AAAA-MM-DD."})


def periodo_em_utc(data_inicio, data_fim, fuso):
    """Converte o período (datas AAAA-MM-DD, no fuso da empresa) em (inicio, fim) UTC.

    `inicio` é o começo do dia de data_inicio; `fim` é o começo do dia SEGUINTE a data_fim
    (limite exclusivo, então o dia final entra inteiro). Datas ausentes viram None.
    422 se o formato for inválido ou data_fim vier antes de data_inicio.
    """
    d_ini = _parse_data(data_inicio, "data_inicio") if data_inicio else None
    d_fim = _parse_data(data_fim, "data_fim") if data_fim else None
    if d_ini and d_fim and d_fim < d_ini:
        raise DadosInvalidosError({"data_fim": "deve ser igual ou posterior a data_inicio."})

    inicio = fim = None
    if d_ini:
        inicio = datetime.combine(d_ini, time.min, tzinfo=fuso).astimezone(timezone.utc)
    if d_fim:
        fim = datetime.combine(d_fim + timedelta(days=1), time.min, tzinfo=fuso).astimezone(timezone.utc)
    return inicio, fim


def montar_pagina(itens: list, limit: int, offset: int, tem_mais: bool) -> dict:
    """Envelope de uma página: itens, indicador de próxima página e o offset para pedi-la."""
    return {
        "itens": itens,
        "tem_mais": tem_mais,
        "limit": limit,
        "offset": offset,
        "proximo_offset": offset + limit if tem_mais else None,
    }