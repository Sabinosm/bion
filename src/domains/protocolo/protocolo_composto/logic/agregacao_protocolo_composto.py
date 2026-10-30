"""agregacao_protocolo_composto.py

Agrega as saídas de vários módulos calculados em UM resultado, conforme o tipo
de agregação do protocolo (soma, máximo, pior categoria, qualquer alerta ou
nenhuma). Funções puras: (list[ResultadoModulo]) -> ResultadoAgregado.

Módulos "nao_calculavel" ou "nao_aplicavel" NUNCA entram como zero: são
excluídos e sinalizados (agregação parcial), pois contar como zero
subestimaria o risco em silêncio.

Cada agregação só aceita o tipo_saida compatível. O seed já garante isso, mas
a checagem é repetida em runtime como segunda linha de defesa.
"""
from typing import Callable

from pydantic import BaseModel

from ...shared.exceptions_protocolo import ConfiguracaoProtocoloInvalidaError
from ..schemas.protocolo_composto_schemas import (
    CLASSIFICACAO_MULTIPLOS_RESULTADOS,
    ResultadoModulo,
    TipoAgregacao,
)


class ResultadoAgregado(BaseModel):
    classificacao: str
    valor: float | str | bool | None = None
    gravidade: int | None = None
    parcial: bool = False              # True se algum módulo do grupo não entrou
    modulos_excluidos: list[str] = []  # siglas dos não calculáveis/não aplicáveis


class AgregacaoInvalida(ConfiguracaoProtocoloInvalidaError):
    """Erro de configuração: agregação incompatível com o tipo_saida dos
    módulos do grupo."""

    MENSAGEM_PADRAO = "A agregação configurada para este protocolo é incompatível com seus módulos. Contate o suporte."


def _calculaveis(modulos: list[ResultadoModulo]) -> tuple[list[ResultadoModulo], list[str]]:
    ok = [m for m in modulos if m.status == "calculado"]
    excluidos = [m.sigla_modulo for m in modulos if m.status != "calculado"]
    return ok, excluidos


def _checar_tipo(modulos: list[ResultadoModulo], esperado: str, agregacao: str) -> None:
    errados = [m.sigla_modulo for m in modulos if m.tipo_saida != esperado]
    if errados:
        raise AgregacaoInvalida(
            f"agregacao '{agregacao}' exige tipo_saida='{esperado}'; "
            f"modulo(s) incompativel(is): {errados}"
        )


def agregar_soma(modulos: list[ResultadoModulo]) -> ResultadoAgregado:
    _checar_tipo(modulos, "pontos", "soma")
    calculaveis, excluidos = _calculaveis(modulos)
    total = sum(m.valor for m in calculaveis) if calculaveis else 0
    total_exibicao = int(total) if float(total).is_integer() else total
    return ResultadoAgregado(
        classificacao=f"total={total_exibicao}", valor=total,
        parcial=bool(excluidos), modulos_excluidos=excluidos,
    )


def agregar_maximo(modulos: list[ResultadoModulo]) -> ResultadoAgregado:
    _checar_tipo(modulos, "pontos", "maximo")
    calculaveis, excluidos = _calculaveis(modulos)
    if not calculaveis:
        return ResultadoAgregado(
            classificacao="sem_dado", valor=None, parcial=True, modulos_excluidos=excluidos,
        )
    maior = max(calculaveis, key=lambda m: m.valor)
    return ResultadoAgregado(
        classificacao=f"maximo={maior.valor}", valor=maior.valor,
        parcial=bool(excluidos), modulos_excluidos=excluidos,
    )


def agregar_pior_categoria(modulos: list[ResultadoModulo]) -> ResultadoAgregado:
    _checar_tipo(modulos, "categoria", "pior_categoria")
    calculaveis, excluidos = _calculaveis(modulos)
    sem_gravidade = [m.sigla_modulo for m in calculaveis if m.gravidade is None]
    if sem_gravidade:
        raise AgregacaoInvalida(
            f"pior_categoria exige 'gravidade' em toda categoria; "
            f"modulo(s) sem gravidade: {sem_gravidade}"
        )
    if not calculaveis:
        return ResultadoAgregado(
            classificacao="sem_dado", valor=None, parcial=True, modulos_excluidos=excluidos,
        )
    pior = max(calculaveis, key=lambda m: m.gravidade)
    return ResultadoAgregado(
        classificacao=pior.classificacao, valor=pior.classificacao, gravidade=pior.gravidade,
        parcial=bool(excluidos), modulos_excluidos=excluidos,
    )


def agregar_any_flag(modulos: list[ResultadoModulo]) -> ResultadoAgregado:
    _checar_tipo(modulos, "flag", "any_flag")
    calculaveis, excluidos = _calculaveis(modulos)
    algum_true = any(m.valor is True for m in calculaveis)
    return ResultadoAgregado(
        classificacao="alerta" if algum_true else "sem_alerta", valor=algum_true,
        parcial=bool(excluidos), modulos_excluidos=excluidos,
    )


def agregar_nenhuma(modulos: list[ResultadoModulo]) -> ResultadoAgregado:
    """Modo paralelo: não há resultado combinado. Usa a classificação
    convencional CLASSIFICACAO_MULTIPLOS_RESULTADOS, que o front reconhece para
    renderizar metadata['modulos'] em destaque."""
    _, excluidos = _calculaveis(modulos)
    return ResultadoAgregado(
        classificacao=CLASSIFICACAO_MULTIPLOS_RESULTADOS,
        parcial=bool(excluidos), modulos_excluidos=excluidos,
    )


AGREGADORES: dict[TipoAgregacao, Callable[[list[ResultadoModulo]], ResultadoAgregado]] = {
    "nenhuma": agregar_nenhuma,
    "soma": agregar_soma,
    "maximo": agregar_maximo,
    "pior_categoria": agregar_pior_categoria,
    "any_flag": agregar_any_flag,
}


def agregar(tipo: TipoAgregacao, modulos: list[ResultadoModulo]) -> ResultadoAgregado:
    """Agrega a lista de resultados conforme o tipo.

    A filtragem (só papel != 'gatilho' e com grupo_agregacao) é do chamador, que
    conhece ModuloDef; aqui se recebe a lista já filtrada.

    Raises:
        AgregacaoInvalida: se o tipo for desconhecido ou incompatível com os módulos.
    """
    fn = AGREGADORES.get(tipo)
    if fn is None:
        raise AgregacaoInvalida(f"tipo de agregacao desconhecido: {tipo!r}")
    return fn(modulos)
