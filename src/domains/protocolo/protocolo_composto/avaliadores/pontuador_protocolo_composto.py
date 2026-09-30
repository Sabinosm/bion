"""Avaliador da familia PONTUADOR: soma pontos de cada parametro (por faixa
ou por mapeamento categorico) e aplica a interpretacao final, se houver.

Funcao pura: (ModuloDef, dados) -> ResultadoModulo. Nunca acessa banco.
"""
from ..schemas.config_schemas import ConfigPontuador, Faixa, InterpretacaoSegmentada
from ..schemas import ItemTrilha, ModuloDef, ResultadoModulo


class ValorNaoComparavel(Exception):
    """O valor recebido nao pode ser comparado numericamente (ex.: texto
    onde se esperava numero). Erro de DADO DE ENTRADA, nao de configuracao:
    o chamador trata como variavel ausente, nunca deixa a excecao subir."""


def _faixa_para(valor: float, faixas: list[Faixa]) -> Faixa | None:
    for f in faixas:
        try:
            piso_ok = f.min is None or valor >= f.min
            teto_ok = f.max is None or valor < f.max
        except TypeError as ex:
            raise ValorNaoComparavel(str(ex)) from ex
        if piso_ok and teto_ok:
            return f
    return None  # so ocorre se o seed nao cobriu o dominio plausivel


def avaliar_pontuador(modulo: ModuloDef, dados: dict) -> ResultadoModulo:
    config = ConfigPontuador.model_validate(modulo.configuracao)

    total = 0
    trilha: list[ItemTrilha] = []
    ausentes: list[str] = []

    for p in config.parametros:
        valor = dados.get(p.variavel)
        if valor is None:
            ausentes.append(p.variavel)
            continue

        if p.tipo == "faixas":
            try:
                faixa = _faixa_para(valor, p.faixas)
            except ValorNaoComparavel:
                # valor de entrada incompativel (ex.: texto): trata como
                # ausente, nunca deixa a excecao subir para o chamador
                ausentes.append(p.variavel)
                continue
            if faixa is None:
                # dominio nao coberto pelo seed: nao adivinha, marca ausente
                ausentes.append(p.variavel)
                continue
            pontos = faixa.pontos
            trilha.append(ItemTrilha(
                rotulo=f"{modulo.sigla} · {p.variavel}",
                valor_observado=str(valor),
                contribuicao=f"+{pontos} pontos",
            ))
        else:  # mapeamento
            chave = str(valor)
            if chave not in p.mapa:
                ausentes.append(p.variavel)
                continue
            pontos = p.mapa[chave]
            trilha.append(ItemTrilha(
                rotulo=f"{modulo.sigla} · {p.variavel}",
                valor_observado=str(valor),
                contribuicao=f"+{pontos} pontos",
            ))

        total += pontos

    obrigatorias = {v for v, obrig in modulo.campos if obrig}
    if obrigatorias & set(ausentes):
        return ResultadoModulo(
            sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
            tipo_saida=modulo.tipo_saida, ausentes=ausentes,
            motivo="variavel(is) obrigatoria(s) ausente(s)",
        )

    classificacao = None
    gravidade = None
    if config.interpretacao is not None:
        if isinstance(config.interpretacao, InterpretacaoSegmentada):
            chave_segmento = dados.get(config.interpretacao.segmentada_por)
            interpretacao_efetiva = config.interpretacao.por_valor.get(str(chave_segmento)) if chave_segmento is not None else None
            if interpretacao_efetiva is None:
                # variavel de segmentacao ausente ou valor sem interpretacao
                # mapeada: sem ela nao ha total interpretavel -- o modulo
                # inteiro fica nao_calculavel (nao "calculado sem classificacao")
                ausentes.append(config.interpretacao.segmentada_por)
                return ResultadoModulo(
                    sigla_modulo=modulo.sigla, versao=modulo.versao, status="nao_calculavel",
                    tipo_saida=modulo.tipo_saida, ausentes=ausentes,
                    motivo="variável de segmentação da interpretação ausente ou com valor não mapeado",
                )
        else:
            interpretacao_efetiva = config.interpretacao

        faixa_final = _faixa_para(total, interpretacao_efetiva.faixas)
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
