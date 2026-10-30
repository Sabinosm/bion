"""pontuador_protocolo_composto.py

Avaliador da família PONTUADOR: soma os pontos de cada parâmetro (por faixa ou
por mapeamento categórico) e aplica a interpretação final do total, quando
houver (inclusive a segmentada por uma variável de entrada). Função pura de
(módulo, dados) para o resultado do módulo; nunca acessa o banco.
"""
from ..schemas.config_schemas import (
    ConfigPontuador,
    Faixa,
    InterpretacaoPontuador,
    InterpretacaoSegmentada,
    ParametroFaixas,
    ParametroMapeamento,
)
from ..schemas.protocolo_composto_schemas import ItemTrilha, ModuloDef, ResultadoModulo
from .comum_protocolo_composto import resultado_nao_calculavel


class ValorNaoComparavel(Exception):
    """O valor recebido não pode ser comparado numericamente (ex.: texto onde se
    esperava número). Erro de DADO DE ENTRADA, não de configuração: o chamador
    trata como variável ausente e nunca deixa a exceção subir."""


def _faixa_para(valor: float, faixas: list[Faixa]) -> Faixa | None:
    """Faixa [min, max) que contém o valor, ou None se o seed não cobriu o domínio."""
    for f in faixas:
        try:
            piso_ok = f.min is None or valor >= f.min
            teto_ok = f.max is None or valor < f.max
        except TypeError as ex:
            raise ValorNaoComparavel(str(ex)) from ex
        if piso_ok and teto_ok:
            return f
    return None


def _pontos_do_parametro(parametro: ParametroFaixas | ParametroMapeamento, valor) -> float | None:
    """Pontos do parâmetro para o valor, ou None se não for pontuável (tratado
    como ausente: valor incomparável, fora do domínio ou sem mapeamento)."""
    if parametro.tipo == "faixas":
        try:
            faixa = _faixa_para(valor, parametro.faixas)
        except ValorNaoComparavel:
            return None
        return None if faixa is None else faixa.pontos
    return parametro.mapa.get(str(valor))


def _resolver_interpretacao(
    interpretacao: InterpretacaoPontuador | InterpretacaoSegmentada, dados: dict
) -> InterpretacaoPontuador | None:
    """Interpretação efetiva. Na segmentada, escolhe o conjunto de faixas pelo
    valor da variável de segmentação; devolve None se ela estiver ausente ou
    sem interpretação mapeada."""
    if isinstance(interpretacao, InterpretacaoSegmentada):
        chave = dados.get(interpretacao.segmentada_por)
        return interpretacao.por_valor.get(str(chave)) if chave is not None else None
    return interpretacao


def avaliar_pontuador(modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    config = ConfigPontuador.model_validate(modulo.configuracao)

    total = 0
    trilha: list[ItemTrilha] = []
    ausentes: list[str] = []

    for p in config.parametros:
        valor = dados.get(p.variavel)
        pontos = None if valor is None else _pontos_do_parametro(p, valor)
        if pontos is None:
            ausentes.append(p.variavel)
            continue

        trilha.append(ItemTrilha(
            rotulo=f"{modulo.sigla} · {p.variavel}",
            valor_observado=str(valor),
            contribuicao=f"+{pontos} pontos",
        ))
        total += pontos

    obrigatorias = {v for v, obrig in modulo.campos if obrig}
    if obrigatorias & set(ausentes):
        return resultado_nao_calculavel(modulo, ausentes, "variavel(is) obrigatoria(s) ausente(s)")

    classificacao = None
    gravidade = None
    if config.interpretacao is not None:
        interpretacao = _resolver_interpretacao(config.interpretacao, dados)
        if interpretacao is None:
            # Variável de segmentação ausente ou sem valor mapeado: sem ela não há
            # total interpretável, então o módulo inteiro fica nao_calculavel
            # (e não "calculado sem classificação").
            ausentes.append(config.interpretacao.segmentada_por)
            return resultado_nao_calculavel(
                modulo, ausentes, "variável de segmentação da interpretação ausente ou com valor não mapeado"
            )

        faixa_final = _faixa_para(total, interpretacao.faixas)
        if faixa_final is not None:
            classificacao = faixa_final.classificacao
            gravidade = faixa_final.gravidade
            trilha.append(ItemTrilha(
                rotulo=f"{modulo.sigla} · total",
                valor_observado=str(total),
                contribuicao=classificacao,
            ))

    return ResultadoModulo(
        sigla_modulo=modulo.sigla, versao=modulo.versao, status="calculado",
        tipo_saida=modulo.tipo_saida, valor=total,
        classificacao=classificacao, gravidade=gravidade,
        trilha=trilha, ausentes=ausentes,
    )
