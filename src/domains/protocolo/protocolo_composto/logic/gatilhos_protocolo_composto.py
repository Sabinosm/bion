"""Aplica `regra_gatilho_json` (nivel do protocolo) sobre os resultados dos
modulos-gatilho ja calculados, decidindo quais modulos ficam 'nao_aplicavel'.

Formato de regra_gatilho_json:
    {
      "gatilhos": [
        {
          "modulo": "<sigla do modulo-gatilho>",
          "quando_classificacao": ["<classificacao 1>", "<classificacao 2>", ...],
          "desliga": ["<sigla 1>", "<sigla 2>", ...],
          "motivo": "<texto exibido nos modulos desligados>"
        },
        ...
      ]
    }

Funcao pura: (regra_gatilho_json, {sigla: ResultadoModulo}) -> {sigla: motivo}.
"""
from ..schemas.protocolo_composto_schemas import ResultadoModulo


class GatilhoInvalido(ValueError):
    """Erro de configuracao: regra_gatilho_json malformado ou referenciando
    modulo inexistente. Deveria ser pego no seed (SQL V... + teste), esta
    checagem aqui e a segunda linha de defesa em runtime."""


def aplicar_gatilhos(
    regra_gatilho_json: dict | None,
    resultados_gatilho: dict[str, ResultadoModulo],
) -> dict[str, str]:
    """Devolve {sigla_do_modulo_desligado: motivo}. Vazio se nao ha
    regra_gatilho_json ou se nenhum gatilho disparou o desligamento.

    Se o modulo-gatilho referenciado esta 'nao_calculavel' (condicao nao
    pode ser avaliada por falta de dado), o gatilho NAO desliga nada --
    nao assume nem elegivel nem inelegivel; os modulos dependentes seguem
    para calculo normal e podem, por sua vez, ficar 'nao_calculavel' se
    de fato precisarem do mesmo dado.
    """
    if not regra_gatilho_json:
        return {}

    lista = regra_gatilho_json.get("gatilhos")
    if not isinstance(lista, list):
        raise GatilhoInvalido("regra_gatilho_json exige uma lista em 'gatilhos'")

    desligados: dict[str, str] = {}

    for g in lista:
        sigla_gatilho = g.get("modulo")
        quando = g.get("quando_classificacao")
        desliga = g.get("desliga")
        motivo = g.get("motivo", f"desligado pelo gatilho {sigla_gatilho}")

        if not sigla_gatilho or not isinstance(quando, list) or not isinstance(desliga, list):
            raise GatilhoInvalido(f"entrada de gatilho malformada: {g!r}")

        resultado_gatilho = resultados_gatilho.get(sigla_gatilho)
        if resultado_gatilho is None:
            raise GatilhoInvalido(
                f"gatilho '{sigla_gatilho}' nao encontrado entre os modulos "
                f"avaliados (siglas disponiveis: {sorted(resultados_gatilho)})"
            )

        if resultado_gatilho.status == "nao_calculavel":
            continue  # nao assume nada; ver docstring

        if resultado_gatilho.classificacao in quando:
            for sigla_alvo in desliga:
                # se dois gatilhos concordam em desligar o mesmo modulo,
                # mantem o primeiro motivo (determinismo: ordem da lista)
                desligados.setdefault(sigla_alvo, motivo)

    return desligados
