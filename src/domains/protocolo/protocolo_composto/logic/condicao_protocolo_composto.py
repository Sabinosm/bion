"""condicao_protocolo_composto.py

Linguagem de condição compartilhada por classificador e regra. Avalia (e
valida a forma de) condições compostas por comparações e pelos conectivos
"e", "ou" e "nao", sem aritmética, funções ou referência a outros módulos.

    condicao   := comparacao | {"e": [condicao...]} | {"ou": [condicao...]}
                             | {"nao": condicao}
    comparacao := {"variavel": <codigo>, "op": <op>, "valor": <literal>}
    op         := "<" | "<=" | ">" | ">=" | "==" | "!=" | "em" | "nao_em"

LÓGICA DE TRÊS VALORES (True / False / None = desconhecido)
Variável ausente não vira False: vira DESCONHECIDO (None). Sem isso,
"idade >= 60" com idade ausente seria "falso" e um alerta clínico deixaria
de disparar em silêncio. Propagação (Kleene):
    e  : algum False -> False | senão algum None -> None | senão True
    ou : algum True  -> True  | senão algum None -> None | senão False
    nao: nega True/False; None permanece None
O chamador decide o que fazer com None (o módulo vira "nao_calculavel").
"""
import operator
from typing import Any

from ...shared.exceptions_protocolo import ConfiguracaoProtocoloInvalidaError

Tri = bool | None  # True, False ou None (desconhecido)

OPS_COMPARACAO = {"<", "<=", ">", ">=", "==", "!="}
OPS_CONJUNTO = {"em", "nao_em"}
OPS_VALIDOS = OPS_COMPARACAO | OPS_CONJUNTO

_OPERADORES = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "em": lambda obs, ref: obs in ref,
    "nao_em": lambda obs, ref: obs not in ref,
}


class CondicaoInvalida(ConfiguracaoProtocoloInvalidaError):
    """Estrutura de condição malformada (erro de seed, não de paciente)."""

    MENSAGEM_PADRAO = "Uma condição configurada em um módulo deste protocolo está inválida. Contate o suporte."


def _exigir_dict_nao_vazio(condicao: Any) -> None:
    if not isinstance(condicao, dict) or not condicao:
        raise CondicaoInvalida(f"condicao deve ser um dict nao vazio: {condicao!r}")


def _extrair_filhos(condicao: dict[str, Any]) -> tuple[str, list]:
    """Valida um nó "e"/"ou" e devolve (chave, filhos)."""
    chave = "e" if "e" in condicao else "ou"
    if len(condicao) != 1:
        raise CondicaoInvalida(f"no {chave!r} nao aceita chaves extras: {condicao!r}")
    filhos = condicao[chave]
    if not isinstance(filhos, list) or not filhos:
        raise CondicaoInvalida(f"{chave!r} exige lista nao vazia")
    return chave, filhos


def _checar_no_nao(condicao: dict[str, Any]) -> None:
    if len(condicao) != 1:
        raise CondicaoInvalida(f"no 'nao' nao aceita chaves extras: {condicao!r}")


def _validar_comparacao(condicao: dict[str, Any]) -> None:
    """Valida a forma de uma comparação (chaves, operador e tipo do valor)."""
    if {"variavel", "op", "valor"} != set(condicao):
        raise CondicaoInvalida(
            f"comparacao exige exatamente variavel/op/valor: {condicao!r}"
        )
    op = condicao["op"]
    if op not in OPS_VALIDOS:
        raise CondicaoInvalida(f"operador desconhecido: {op!r}")
    if op in OPS_CONJUNTO and not isinstance(condicao["valor"], (list, tuple, set)):
        raise CondicaoInvalida(f"operador {op!r} exige lista em 'valor'")


def _comparar(op: str, obs: Any, ref: Any) -> bool:
    try:
        funcao = _OPERADORES[op]
    except KeyError:
        raise CondicaoInvalida(f"operador desconhecido: {op!r}") from None
    return funcao(obs, ref)


def avaliar(condicao: dict[str, Any], dados: dict[str, Any]) -> Tri:
    """Avalia a condição contra `dados` ({codigo_variavel: valor}).

    Função pura. Retorna True, False ou None (desconhecido).

    Raises:
        CondicaoInvalida: se a condição for malformada ou comparar tipos incompatíveis.
    """
    _exigir_dict_nao_vazio(condicao)

    if "e" in condicao or "ou" in condicao:
        chave, filhos = _extrair_filhos(condicao)
        vals = [avaliar(f, dados) for f in filhos]
        if chave == "e":
            if any(v is False for v in vals):
                return False
            return None if any(v is None for v in vals) else True
        if any(v is True for v in vals):
            return True
        return None if any(v is None for v in vals) else False

    if "nao" in condicao:
        _checar_no_nao(condicao)
        v = avaliar(condicao["nao"], dados)
        return None if v is None else (not v)

    _validar_comparacao(condicao)
    obs = dados.get(condicao["variavel"])
    if obs is None:
        return None
    try:
        return _comparar(condicao["op"], obs, condicao["valor"])
    except TypeError as ex:
        # ex.: comparar str com número. Erro de configuração, não de paciente.
        raise CondicaoInvalida(
            f"tipos incompativeis em {condicao!r} (observado={obs!r})"
        ) from ex


def variaveis_usadas(condicao: dict[str, Any]) -> set[str]:
    """Códigos de variável citados na condição.

    NÃO valida a estrutura (operador, chaves): só extrai o que encontrar.
    Para validar de verdade no seed, use `validar_estrutura`.
    """
    if "e" in condicao or "ou" in condicao:
        filhos = condicao.get("e") or condicao.get("ou")
        return set().union(*(variaveis_usadas(f) for f in filhos))
    if "nao" in condicao:
        return variaveis_usadas(condicao["nao"])
    return {condicao["variavel"]}


def validar_estrutura(condicao: dict[str, Any]) -> set[str]:
    """Valida recursivamente a FORMA da condição, sem precisar de `dados`, e
    devolve o conjunto de variáveis usadas. É o que o seed deve chamar para
    pegar erro de configuração cedo, antes de qualquer execução.

    Raises:
        CondicaoInvalida: se qualquer parte da condição for malformada.
    """
    _exigir_dict_nao_vazio(condicao)

    if "e" in condicao or "ou" in condicao:
        _, filhos = _extrair_filhos(condicao)
        return set().union(*(validar_estrutura(f) for f in filhos))

    if "nao" in condicao:
        _checar_no_nao(condicao)
        return validar_estrutura(condicao["nao"])

    _validar_comparacao(condicao)
    return {condicao["variavel"]}
