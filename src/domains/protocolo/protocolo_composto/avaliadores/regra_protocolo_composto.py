"""Avaliador da familia REGRA/GATILHO: avalia uma condicao unica e devolve
um flag (verdadeiro/falso) com motivo. Usa a mesma linguagem de condicao
do classificador por regras.

Funcao pura: (ModuloDef, dados) -> ResultadoModulo.
"""
from ..logic.condicao_protocolo_composto import avaliar as avaliar_condicao
from ..schemas.config_schemas import ConfigRegra
from ..schemas.protocolo_composto_schemas import ItemTrilha, ModuloDef, ResultadoModulo


def avaliar_regra(modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    config = ConfigRegra.model_validate(modulo.configuracao)
    resultado = avaliar_condicao(config.condicao, dados)

    if resultado is None:
        obrigatorias = {v for v, obrig in modulo.campos if obrig}
        return ResultadoModulo(
            sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
            tipo_saida=modulo.tipo_saida, ausentes=sorted(obrigatorias),
            motivo="dado insuficiente para avaliar a condicao",
        )

    saida = config.saida_verdadeiro if resultado else config.saida_falso
    return ResultadoModulo(
        sigla_modulo=modulo.sigla, versao=modulo.versao, status="calculado",
        tipo_saida=modulo.tipo_saida, valor=resultado,
        classificacao=saida.classificacao, motivo=saida.motivo,
        trilha=[ItemTrilha(
            rotulo=f"{modulo.sigla} · gatilho",
            valor_observado="condicao " + ("verdadeira" if resultado else "falsa"),
            contribuicao=saida.classificacao,
        )],
    )
