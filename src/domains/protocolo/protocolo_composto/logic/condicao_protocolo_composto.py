"""Linguagem de condicao compartilhada por classificador e regra.

    condicao   := comparacao | {"e": [condicao...]} | {"ou": [condicao...]}
                             | {"nao": condicao}
    comparacao := {"variavel": <codigo>, "op": <op>, "valor": <literal>}
    op         := "<" | "<=" | ">" | ">=" | "==" | "!=" | "em" | "nao_em"

Sem aritmetica, sem funcoes, sem referencia a outros modulos.

LOGICA DE TRES VALORES (True / False / None=desconhecido)
Variavel ausente nao vira False: vira DESCONHECIDO (None). Sem isso,
"idade >= 60" com idade ausente seria "falso" e um alerta clinico deixaria
de disparar em silencio. Propagacao (Kleene):
    e  : algum False -> False | senao algum None -> None | senao True
    ou : algum True  -> True  | senao algum None -> None | senao False
    nao: nega True/False; None permanece None
O chamador decide o que fazer com None (o modulo vira "nao_calculavel").
"""
from typing import Any

Tri = bool | None  # True, False ou None (desconhecido)

OPS_COMPARACAO = {"<", "<=", ">", ">=", "==", "!="}
OPS_CONJUNTO = {"em", "nao_em"}
OPS_VALIDOS = OPS_COMPARACAO | OPS_CONJUNTO


class CondicaoInvalida(ValueError):
    """Estrutura de condicao malformada (erro de seed, nao de paciente)."""


def _comparar(op: str, obs: Any, ref: Any) -> bool:
    if op == "<":
        return obs < ref
    if op == "<=":
        return obs <= ref
    if op == ">":
        return obs > ref
    if op == ">=":
        return obs >= ref
    if op == "==":
        return obs == ref
    if op == "!=":
        return obs != ref
    if op == "em":
        return obs in ref
    if op == "nao_em":
        return obs not in ref
    raise CondicaoInvalida(f"operador desconhecido: {op!r}")


def avaliar(condicao: dict[str, Any], dados: dict[str, Any]) -> Tri:
    """Avalia a condicao contra `dados` ({codigo_variavel: valor}).
    Funcao pura. Retorna True, False ou None (desconhecido)."""
    if not isinstance(condicao, dict) or not condicao:
        raise CondicaoInvalida(f"condicao deve ser um dict nao vazio: {condicao!r}")

    if "e" in condicao or "ou" in condicao:
        chave = "e" if "e" in condicao else "ou"
        if len(condicao) != 1:
            raise CondicaoInvalida(f"no {chave!r} nao aceita chaves extras: {condicao!r}")
        filhos = condicao[chave]
        if not isinstance(filhos, list) or not filhos:
            raise CondicaoInvalida(f"{chave!r} exige lista nao vazia")
        vals = [avaliar(f, dados) for f in filhos]
        if chave == "e":
            if any(v is False for v in vals):
                return False
            return None if any(v is None for v in vals) else True
        if any(v is True for v in vals):
            return True
        return None if any(v is None for v in vals) else False

    if "nao" in condicao:
        if len(condicao) != 1:
            raise CondicaoInvalida(f"no 'nao' nao aceita chaves extras: {condicao!r}")
        v = avaliar(condicao["nao"], dados)
        return None if v is None else (not v)

    if {"variavel", "op", "valor"} != set(condicao):
        raise CondicaoInvalida(
            f"comparacao exige exatamente variavel/op/valor: {condicao!r}"
        )
    op = condicao["op"]
    if op not in OPS_VALIDOS:
        raise CondicaoInvalida(f"operador desconhecido: {op!r}")
    if op in OPS_CONJUNTO and not isinstance(condicao["valor"], (list, tuple, set)):
        raise CondicaoInvalida(f"operador {op!r} exige lista em 'valor'")

    obs = dados.get(condicao["variavel"])
    if obs is None:
        return None
    try:
        return _comparar(op, obs, condicao["valor"])
    except TypeError as ex:
        # ex.: comparar str com numero. Erro de configuracao, nao de paciente.
        raise CondicaoInvalida(
            f"tipos incompativeis em {condicao!r} (observado={obs!r})"
        ) from ex


def variaveis_usadas(condicao: dict[str, Any]) -> set[str]:
    """Codigos de variavel citados na condicao. Usado pelo seed para checar
    que variaveis usadas == variaveis declaradas no modulo.

    NAO valida a estrutura (operador, chaves) -- so extrai o que encontrar.
    Para validar a condicao de verdade no seed, use `validar_estrutura`."""
    if "e" in condicao or "ou" in condicao:
        filhos = condicao.get("e") or condicao.get("ou")
        return set().union(*(variaveis_usadas(f) for f in filhos))
    if "nao" in condicao:
        return variaveis_usadas(condicao["nao"])
    return {condicao["variavel"]}


def validar_estrutura(condicao: dict[str, Any]) -> set[str]:
    """Valida recursivamente a FORMA da condicao (sem precisar de `dados`):
    chaves corretas, operador conhecido, 'em'/'nao_em' com lista em 'valor'.
    Devolve o conjunto de variaveis usadas (equivalente a variaveis_usadas,
    mas so retorna se a estrutura inteira for valida). E o que o seed deve
    chamar para pegar erro de configuracao cedo, antes de qualquer execucao."""
    if not isinstance(condicao, dict) or not condicao:
        raise CondicaoInvalida(f"condicao deve ser um dict nao vazio: {condicao!r}")

    if "e" in condicao or "ou" in condicao:
        chave = "e" if "e" in condicao else "ou"
        if len(condicao) != 1:
            raise CondicaoInvalida(f"no {chave!r} nao aceita chaves extras: {condicao!r}")
        filhos = condicao[chave]
        if not isinstance(filhos, list) or not filhos:
            raise CondicaoInvalida(f"{chave!r} exige lista nao vazia")
        return set().union(*(validar_estrutura(f) for f in filhos))

    if "nao" in condicao:
        if len(condicao) != 1:
            raise CondicaoInvalida(f"no 'nao' nao aceita chaves extras: {condicao!r}")
        return validar_estrutura(condicao["nao"])

    if {"variavel", "op", "valor"} != set(condicao):
        raise CondicaoInvalida(
            f"comparacao exige exatamente variavel/op/valor: {condicao!r}"
        )
    op = condicao["op"]
    if op not in OPS_VALIDOS:
        raise CondicaoInvalida(f"operador desconhecido: {op!r}")
    if op in OPS_CONJUNTO and not isinstance(condicao["valor"], (list, tuple, set)):
        raise CondicaoInvalida(f"operador {op!r} exige lista em 'valor'")

    return {condicao["variavel"]}
