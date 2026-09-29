"""Avaliador da familia CLASSIFICADOR: mapeia variavel(is) para UMA
categoria, por faixa (uma variavel numerica) ou por regras (condicoes
sobre varias variaveis, primeira que casa vence, com 'padrao' como saida).

Funcao pura: (ModuloDef, dados) -> ResultadoModulo.
"""
from ..logic.condicao_protocolo_composto import avaliar as avaliar_condicao
from ..schemas.config_schemas import ClassificadorPorFaixas, ClassificadorPorRegras, validar_configuracao
from ..schemas.protocolo_composto_schemas import ItemTrilha, ModuloDef, ResultadoModulo


def _por_faixas(config: ClassificadorPorFaixas, modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    valor = dados.get(config.variavel)
    if valor is None:
        return ResultadoModulo(
            sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
            tipo_saida=modulo.tipo_saida, ausentes=[config.variavel],
            motivo="variavel obrigatoria ausente",
        )

    for c in config.categorias:
        try:
            piso_ok = c.min is None or valor >= c.min
            teto_ok = c.max is None or valor < c.max
        except TypeError:
            return ResultadoModulo(
                sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
                tipo_saida=modulo.tipo_saida, ausentes=[config.variavel],
                motivo=f"valor {valor!r} nao e comparavel numericamente",
            )
        if piso_ok and teto_ok:
            return ResultadoModulo(
                sigla_modulo=modulo.sigla, versao=modulo.versao, status="calculado",
                tipo_saida=modulo.tipo_saida, valor=c.classificacao,
                classificacao=c.classificacao, gravidade=c.gravidade,
                trilha=[ItemTrilha(
                    rotulo=f"{modulo.sigla} · {config.variavel}",
                    valor_observado=str(valor),
                    contribuicao=c.classificacao,
                )],
            )

    # dominio nao coberto pelo seed: nao adivinha
    return ResultadoModulo(
        sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
        tipo_saida=modulo.tipo_saida, ausentes=[config.variavel],
        motivo=f"valor {valor!r} fora do dominio coberto pelas faixas",
    )


def _por_regras(config: ClassificadorPorRegras, modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    desconhecido_em_alguma = False

    for r in config.regras:
        resultado = avaliar_condicao(r.se, dados)
        if resultado is True:
            return ResultadoModulo(
                sigla_modulo=modulo.sigla, versao=modulo.versao, status="calculado",
                tipo_saida=modulo.tipo_saida, valor=r.classificacao,
                classificacao=r.classificacao, gravidade=r.gravidade,
                trilha=[ItemTrilha(
                    rotulo=f"{modulo.sigla} · regra",
                    valor_observado="condicao satisfeita",
                    contribuicao=r.classificacao,
                )],
            )
        if resultado is None:
            desconhecido_em_alguma = True
        # False: tenta a proxima regra

    if desconhecido_em_alguma:
        # nenhuma regra bateu True, mas alguma ficou indefinida por falta de
        # dado -- nao assume o padrao, pois uma regra mais grave poderia
        # ter batido se o dado existisse.
        obrigatorias = {v for v, obrig in modulo.campos if obrig}
        return ResultadoModulo(
            sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
            tipo_saida=modulo.tipo_saida, ausentes=sorted(obrigatorias),
            motivo="dado insuficiente para decidir entre as regras",
        )

    padrao = config.padrao
    return ResultadoModulo(
        sigla_modulo=modulo.sigla, versao=modulo.versao, status="calculado",
        tipo_saida=modulo.tipo_saida, valor=padrao["classificacao"],
        classificacao=padrao["classificacao"], gravidade=padrao.get("gravidade"),
        trilha=[ItemTrilha(
            rotulo=f"{modulo.sigla} · padrao",
            valor_observado="nenhuma regra satisfeita",
            contribuicao=padrao["classificacao"],
        )],
    )


def avaliar_classificador(modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    config = validar_configuracao("classificador", modulo.configuracao)
    if isinstance(config, ClassificadorPorFaixas):
        return _por_faixas(config, modulo, dados)
    return _por_regras(config, modulo, dados)
