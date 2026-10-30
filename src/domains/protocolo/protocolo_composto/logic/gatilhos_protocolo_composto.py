"""gatilhos_protocolo_composto.py

Aplica a `regra_gatilho_json` (nível do protocolo) sobre os resultados dos
módulos-gatilho já calculados, decidindo quais módulos ficam "nao_aplicavel".

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

Função pura: (regra_gatilho_json, {sigla: ResultadoModulo}) -> {sigla: motivo}.
"""
from ...shared.exceptions_protocolo import ConfiguracaoProtocoloInvalidaError
from ..schemas.protocolo_composto_schemas import ResultadoModulo


class GatilhoInvalido(ConfiguracaoProtocoloInvalidaError):
    """Erro de configuração: regra_gatilho_json malformado ou referenciando
    módulo inexistente. Segunda linha de defesa em runtime; deveria ser pego
    no seed."""

    MENSAGEM_PADRAO = "A regra de gatilho configurada para este protocolo está inválida. Contate o suporte."


def aplicar_gatilhos(
    regra_gatilho_json: dict | None,
    resultados_gatilho: dict[str, ResultadoModulo],
) -> dict[str, str]:
    """Devolve {sigla_do_modulo_desligado: motivo}.

    Vazio se não há regra_gatilho_json ou se nenhum gatilho disparou. Se o
    módulo-gatilho está "nao_calculavel" (falta de dado), o gatilho NÃO desliga
    nada: não assume elegível nem inelegível, e os módulos dependentes seguem
    para cálculo normal (podendo ficar "nao_calculavel" se precisarem do mesmo
    dado). Se dois gatilhos desligam o mesmo módulo, vale o primeiro motivo.

    Raises:
        GatilhoInvalido: se a regra for malformada ou citar gatilho não avaliado.
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
            continue

        if resultado_gatilho.classificacao in quando:
            for sigla_alvo in desliga:
                desligados.setdefault(sigla_alvo, motivo)

    return desligados
