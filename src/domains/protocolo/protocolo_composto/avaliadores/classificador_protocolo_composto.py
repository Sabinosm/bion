"""classificador_protocolo_composto.py

Avaliador da família CLASSIFICADOR: mapeia variáveis para UMA categoria, seja
por faixas (uma variável numérica) ou por regras (condições sobre várias
variáveis; a primeira que casa vence e há uma saída padrão). Função pura de
(módulo, dados) para o resultado do módulo; nunca acessa o banco.
"""
from ..logic.condicao_protocolo_composto import avaliar as avaliar_condicao
from ..schemas.config_schemas import ClassificadorPorFaixas, ClassificadorPorRegras, validar_configuracao
from ..schemas.protocolo_composto_schemas import ItemTrilha, ModuloDef, ResultadoModulo
from .comum_protocolo_composto import resultado_nao_calculavel


def _resultado_calculado(modulo: ModuloDef, rotulo: str, valor_observado: str,
                         classificacao: str, gravidade: int | None) -> ResultadoModulo:
    return ResultadoModulo(
        sigla_modulo=modulo.sigla, versao=modulo.versao, status="calculado",
        tipo_saida=modulo.tipo_saida, valor=classificacao,
        classificacao=classificacao, gravidade=gravidade,
        trilha=[ItemTrilha(
            rotulo=f"{modulo.sigla} · {rotulo}",
            valor_observado=valor_observado,
            contribuicao=classificacao,
        )],
    )


def _por_faixas(config: ClassificadorPorFaixas, modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    valor = dados.get(config.variavel)
    if valor is None:
        return resultado_nao_calculavel(modulo, [config.variavel], "variavel obrigatoria ausente")

    for c in config.categorias:
        try:
            piso_ok = c.min is None or valor >= c.min
            teto_ok = c.max is None or valor < c.max
        except TypeError:
            return resultado_nao_calculavel(
                modulo, [config.variavel], f"valor {valor!r} nao e comparavel numericamente"
            )
        if piso_ok and teto_ok:
            return _resultado_calculado(modulo, config.variavel, str(valor), c.classificacao, c.gravidade)

    # Domínio não coberto pelo seed: não adivinha.
    return resultado_nao_calculavel(
        modulo, [config.variavel], f"valor {valor!r} fora do dominio coberto pelas faixas"
    )


def _por_regras(config: ClassificadorPorRegras, modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    desconhecido_em_alguma = False

    for r in config.regras:
        resultado = avaliar_condicao(r.se, dados)
        if resultado is True:
            return _resultado_calculado(modulo, "regra", "condicao satisfeita", r.classificacao, r.gravidade)
        if resultado is None:
            desconhecido_em_alguma = True
        # False: tenta a próxima regra

    if desconhecido_em_alguma:
        # Nenhuma regra bateu True, mas alguma ficou indefinida por falta de dado.
        # Não assume o padrão: uma regra mais grave poderia ter batido se o dado existisse.
        obrigatorias = {v for v, obrig in modulo.campos if obrig}
        return resultado_nao_calculavel(
            modulo, sorted(obrigatorias), "dado insuficiente para decidir entre as regras"
        )

    padrao = config.padrao
    return _resultado_calculado(
        modulo, "padrao", "nenhuma regra satisfeita", padrao["classificacao"], padrao.get("gravidade")
    )


def avaliar_classificador(modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    config = validar_configuracao("classificador", modulo.configuracao)
    if isinstance(config, ClassificadorPorFaixas):
        return _por_faixas(config, modulo, dados)
    return _por_regras(config, modulo, dados)
