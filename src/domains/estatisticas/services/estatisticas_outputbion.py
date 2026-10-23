"""
estatisticas_outputbion.py

Estatísticas de qualidade da IA a partir das execuções do Bion: confiança e
completude médias dos dados de entrada, versões do modelo em uso e correlação
entre as duas primeiras. Confiança e completude são percentuais com
interpretação completa (mais é melhor) e comparação com o período anterior. As
versões em uso são apenas informativas. A correlação é um coeficiente de
-1 a 1, sem nível, e só descreve associação, não causalidade.
"""

from src.domains.avaliacao_bion.service import OutputBionService
from src.domains.estatisticas.interpretacao_helper import (
    interpretacao_percentual, interpretacao_sem_nivel, calcular_comparacao, valor_periodo_anterior,
)

_output_bion_svc = OutputBionService()


def _resposta_media(media, dias, leitura, texto, buscar_anterior):
    """Monta a resposta padrão de uma média percentual da IA (confiança, completude).

    Args:
        media: média do período atual, ou None se não houve execuções.
        dias: duração do período, devolvida na resposta.
        leitura: modelo de texto com {media} e {dias}.
        texto: explicação da interpretação.
        buscar_anterior: função sem argumentos que devolve a média do período
            anterior; só é chamada quando há média atual.
    """
    if media is None:
        return {"media": None, "dias": dias, "leitura": "Sem execuções da IA no período", "interpretacao": None}

    interpretacao = interpretacao_percentual(
        valor=media,
        texto=texto,
        direcao="alto_bom",
        comparacao=calcular_comparacao(media, buscar_anterior()),
    )

    return {
        "media": round(media, 2),
        "dias": dias,
        "leitura": leitura.format(media=round(media, 1), dias=dias),
        "interpretacao": interpretacao,
    }


def _coeficiente_pearson(pares):
    """Coeficiente de Pearson (3 casas) dos pares (x, y), ou None se x ou y não variam."""
    n = len(pares)
    xs = [p[0] for p in pares]
    ys = [p[1] for p in pares]
    media_x = sum(xs) / n
    media_y = sum(ys) / n

    cov = sum((x - media_x) * (y - media_y) for x, y in pares)
    var_x = sum((x - media_x) ** 2 for x in xs)
    var_y = sum((y - media_y) ** 2 for y in ys)

    if var_x == 0 or var_y == 0:
        return None

    return round(cov / (var_x ** 0.5 * var_y ** 0.5), 3)


def _descrever_correlacao(coeficiente: float) -> str:
    """Rótulo de força (pelo valor absoluto) e sentido da correlação.

    Força: 0.7+ forte, 0.4+ moderada, 0.1+ fraca, abaixo disso praticamente nula
    (sem sentido). Ex.: "forte positiva", "moderada negativa".
    """
    forca = abs(coeficiente)
    if forca >= 0.7:
        rotulo = "forte"
    elif forca >= 0.4:
        rotulo = "moderada"
    elif forca >= 0.1:
        rotulo = "fraca"
    else:
        return "praticamente nula"
    sentido = "positiva" if coeficiente > 0 else "negativa"
    return f"{rotulo} {sentido}"


class EstatisticasOutputBion:

    def confianca_media(self, id_empresa, dias=30):
        """Confiança média das execuções da IA no período, com interpretação
        completa (B1).

        Retorna: {"media": float|None, "dias": int, "leitura": str, "interpretacao": {...}|None}
        """
        media = _output_bion_svc.media_confianca(id_empresa=id_empresa, dias=dias)

        return _resposta_media(
            media, dias,
            leitura="Confiança média da IA nos últimos {dias} dias: {media}%",
            texto="Alto = IA decidindo com segurança; baixo = revisar qualidade dos dados de entrada ou performance do modelo",
            buscar_anterior=lambda: valor_periodo_anterior(_output_bion_svc.media_confianca_periodo, id_empresa, dias),
        )

    def completude_media(self, id_empresa, dias=30):
        """Completude média dos dados de entrada usados pela IA no período,
        com interpretação completa (B2).

        Retorna: {"media": float|None, "dias": int, "leitura": str, "interpretacao": {...}|None}
        """
        media = _output_bion_svc.media_completude(id_empresa=id_empresa, dias=dias)

        return _resposta_media(
            media, dias,
            leitura="Completude média dos dados de entrada: {media}%",
            texto="Alto = profissionais preenchendo os dados de entrada de forma completa; baixo = triagem apressada ou campos obrigatórios sendo pulados",
            buscar_anterior=lambda: valor_periodo_anterior(_output_bion_svc.media_completude_periodo, id_empresa, dias),
        )

    def versoes_em_uso(self, id_empresa, dias=30):
        """Versões do modelo de IA usadas no período (B4).

        Sem interpretação: é informativo/rastreabilidade, não tem lado
        bom/ruim uma versão específica estar em uso.
        """
        versoes = _output_bion_svc.versoes_em_uso(id_empresa=id_empresa, dias=dias)

        leitura = None
        if versoes:
            principal = versoes[0]
            if len(versoes) == 1:
                leitura = f"Todas as execuções usaram o modelo {principal['versao_modelo_ia']}"
            else:
                leitura = (
                    f"{len(versoes)} versões de modelo em uso no período -- "
                    f"predominante: {principal['versao_modelo_ia']} ({principal['total']} execuções)"
                )

        return {"versoes": versoes, "leitura": leitura}

    def correlacao_completude_confianca(self, id_empresa, dias=30):
        """Correlação de Pearson entre completude e confiança da IA (E3).

        Caso especial: o coeficiente vai de -1 a 1, não é uma escala
        0-100, então não usa nível por percentual. `direcao` é sempre
        'neutro' — correlação alta não é "boa" nem "ruim" por si só, é
        só informação de quão ligadas as duas métricas estão.

        Retorna: {"coeficiente": float|None, "n_amostras": int, "leitura": str, "interpretacao": {...}|None}
        """
        pares = _output_bion_svc.pares_completude_confianca(id_empresa=id_empresa, dias=dias)

        n = len(pares)
        if n < 2:
            return {"coeficiente": None, "n_amostras": n, "leitura": "Amostra insuficiente para calcular correlação", "interpretacao": None}

        coeficiente = _coeficiente_pearson(pares)
        if coeficiente is None:
            return {"coeficiente": None, "n_amostras": n, "leitura": "Sem variação suficiente nos dados para calcular correlação", "interpretacao": None}

        leitura = f"Correlação {_descrever_correlacao(coeficiente)} entre completude e confiança (r={coeficiente}, n={n})"

        if coeficiente <= -0.1:
            texto = "Correlação negativa sugere que mais completude dos dados de entrada coincide com menor confiança da IA -- vale investigar; não indica causalidade, só associação"
        else:
            texto = "Correlação forte sugere que melhorar a completude dos dados de entrada tende a elevar a confiança da IA -- não indica causalidade, só associação"
        interpretacao = interpretacao_sem_nivel(texto=texto)

        return {"coeficiente": coeficiente, "n_amostras": n, "leitura": leitura, "interpretacao": interpretacao}