"""Mapeamento de UF para fuso horário IANA.

Usado para calcular "hoje" no fuso da empresa (não em UTC) nas
métricas diárias -- ver Empresa.fuso_horario.

O Brasil não usa mais horário de verão desde a suspensão em 2019, então
cada UF tem um único offset fixo o ano todo. A maioria das UFs está em
UTC-3 (America/Sao_Paulo); as exceções abaixo cobrem os estados com
offset diferente.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

FUSO_PADRAO = "America/Sao_Paulo"  # UTC-3, usado pela maioria das UFs

UF_PARA_FUSO = {
    "AC": "America/Rio_Branco",    # UTC-5
    "AM": "America/Manaus",        # UTC-4 (maior parte do estado)
    "MT": "America/Cuiaba",        # UTC-4
    "MS": "America/Campo_Grande",  # UTC-4
    "RR": "America/Boa_Vista",     # UTC-4
    "RO": "America/Porto_Velho",   # UTC-4
    "PA": "America/Belem",         # UTC-3 (maior parte do estado)
    # Demais UFs (SP, RJ, MG, ES, BA, ..., DF) -- UTC-3, fuso padrão.
}


def fuso_por_uf(uf: str | None) -> ZoneInfo:
    """Devolve o ZoneInfo do fuso horário oficial da UF informada, ou
    o fuso padrão (America/Sao_Paulo, UTC-3) se a UF for None ou não
    estiver no mapeamento (dado legado, região sem UF preenchida).
    """
    nome_fuso = UF_PARA_FUSO.get(uf, FUSO_PADRAO) if uf else FUSO_PADRAO
    return ZoneInfo(nome_fuso)


def offset_str_por_uf(uf: str | None) -> str:
    """Devolve o offset fixo da UF como string "+HH:MM"/"-HH:MM",
    pronta para uso em CONVERT_TZ() do MySQL.

    Usa offset numérico (não o nome do fuso, tipo 'America/Sao_Paulo')
    de propósito: CONVERT_TZ() com nome de fuso exige que as tabelas
    mysql.time_zone_name estejam carregadas no servidor, o que nem
    todo provedor gerenciado garante. Offset numérico funciona sempre,
    sem depender dessas tabelas -- seguro aqui porque o Brasil não tem
    mais horário de verão (desde 2019), então o offset de cada UF é
    constante o ano todo.
    """
    fuso = fuso_por_uf(uf)
    offset = datetime.now(fuso).utcoffset()
    total_minutos = int(offset.total_seconds() // 60)
    sinal = "+" if total_minutos >= 0 else "-"
    total_minutos = abs(total_minutos)
    horas, minutos = divmod(total_minutos, 60)
    return f"{sinal}{horas:02d}:{minutos:02d}"