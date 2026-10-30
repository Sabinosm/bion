"""regra_protocolo_composto.py

Avaliador da família REGRA/GATILHO: avalia uma única condição e devolve um
flag (verdadeiro/falso) com a classificação e o motivo configurados para cada
saída. Usa a mesma linguagem de condição do classificador por regras. Função
pura de (módulo, dados) para o resultado do módulo.
"""
from ..logic.condicao_protocolo_composto import avaliar as avaliar_condicao
from ..schemas.config_schemas import ConfigRegra
from ..schemas.protocolo_composto_schemas import ItemTrilha, ModuloDef, ResultadoModulo
from .comum_protocolo_composto import resultado_nao_calculavel


def avaliar_regra(modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    config = ConfigRegra.model_validate(modulo.configuracao)
    resultado = avaliar_condicao(config.condicao, dados)

    if resultado is None:
        obrigatorias = {v for v, obrig in modulo.campos if obrig}
        return resultado_nao_calculavel(
            modulo, sorted(obrigatorias), "dado insuficiente para avaliar a condicao"
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
