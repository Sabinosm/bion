"""
interpretacao_helper.py

Utilitários compartilhados para montar o campo "interpretacao" dos retornos
de estatística. Aqui ficam a classificação de percentuais em níveis de
qualidade (do "otimo" ao "ruim", com a escala podendo ser invertida para
métricas em que valor alto é ruim), a montagem do dicionário de interpretação
(com ou sem nível), o texto de comparação com o período anterior e o cálculo
do valor do período imediatamente anterior, com a mesma duração e sem
sobreposição. É usado pelos serviços de estatística; as rotas não o chamam
diretamente.
"""

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

_DIRECOES_PERCENTUAL = {"alto_bom", "alto_ruim"}


def nivel_por_percentual(valor: float) -> str:
    """Classifica um valor de 0 a 100 em nível.

    Limiares: 85+ otimo, 70+ bom, 60+ ok, 50+ medio, 40+ medio_ruim, abaixo de 40 ruim.
    Para métricas em que valor ALTO é bom (ex.: taxa de conclusão, confiança da IA).
    Quando valor ALTO é ruim, usar nivel_por_percentual_invertido.
    """
    if valor >= 85:
        return "otimo"
    if valor >= 70:
        return "bom"
    if valor >= 60:
        return "ok"
    if valor >= 50:
        return "medio"
    if valor >= 40:
        return "medio_ruim"
    return "ruim"


def nivel_por_percentual_invertido(valor: float) -> str:
    """Mesmos limiares de nivel_por_percentual, com a escala invertida.

    Para métricas em que valor ALTO é ruim (ex.: % de reações alérgicas graves,
    % de abandono): 5% é "otimo" e 90% é "ruim".
    """
    return nivel_por_percentual(100 - valor)


def interpretacao_percentual(
    valor: float,
    texto: str,
    direcao: str = "alto_bom",
    comparacao: Optional[str] = None,
) -> dict:
    """Monta a interpretação de uma métrica percentual (0 a 100) com limiar conhecido.

    Args:
        valor: percentual medido.
        texto: explicação em linguagem natural do resultado.
        direcao: "alto_bom" (mais é melhor) ou "alto_ruim" (mais é pior, usa a
            escala invertida).
        comparacao: texto de comparação com o período anterior, se houver.

    Returns:
        {"direcao", "texto", "nivel", "comparacao"}

    Raises:
        ValueError: se `direcao` não for "alto_bom" nem "alto_ruim".
    """
    if direcao not in _DIRECOES_PERCENTUAL:
        raise ValueError(f"direcao inválida: '{direcao}'. Valores aceitos: {sorted(_DIRECOES_PERCENTUAL)}.")
    nivel = nivel_por_percentual_invertido(valor) if direcao == "alto_ruim" else nivel_por_percentual(valor)
    return {
        "direcao": direcao,
        "texto": texto,
        "nivel": nivel,
        "comparacao": comparacao,
    }


def interpretacao_sem_nivel(texto: str, direcao: str = "neutro", comparacao: Optional[str] = None) -> dict:
    """Monta a interpretação de métricas sem limiar absoluto (volume, contagem, tempo médio).

    O nível é sempre None: não existe "85 atendimentos é ótimo", pois depende
    de um contexto que o sistema não tem. Direção e comparação ainda agregam valor.

    Returns:
        {"direcao", "texto", "nivel": None, "comparacao"}
    """
    return {
        "direcao": direcao,
        "texto": texto,
        "nivel": None,
        "comparacao": comparacao,
    }


def calcular_comparacao(
    valor_atual: Optional[float],
    valor_anterior: Optional[float],
    unidade: str = "%",
) -> Optional[str]:
    """Texto padrão de comparação com o período anterior.

    Retorna "Aumento de X% ..." ou "Queda de X% ..." (variação arredondada a
    uma casa), "Sem variação ..." quando a variação é zero, e None quando não
    há base de comparação (valor atual ou anterior ausente, ou anterior igual a 0).
    """
    if valor_anterior is None or valor_anterior == 0 or valor_atual is None:
        return None

    variacao = round(((valor_atual - valor_anterior) / valor_anterior) * 100, 1)
    if variacao == 0:
        return "Sem variação em comparação com o período anterior"

    direcao_texto = "Aumento" if variacao > 0 else "Queda"
    return f"{direcao_texto} de {abs(variacao)}% em comparação com o período anterior"


def valor_periodo_anterior(metodo_periodo: Callable, id_empresa: int, dias: int, **kwargs):
    """Obtém a métrica do período anterior: mesma duração, imediatamente antes
    do período atual e sem sobreposição.

    Args:
        metodo_periodo: método de repository/service que aceita id_empresa,
            data_inicio e data_fim (datas em UTC).
        id_empresa: empresa consultada.
        dias: duração do período atual, que define a do anterior.
        **kwargs: parâmetros extras repassados ao método (ex.: codigo_cid10).
    """
    agora = datetime.now(timezone.utc)
    inicio_atual = agora - timedelta(days=dias)
    inicio_anterior = agora - timedelta(days=dias * 2)
    return metodo_periodo(id_empresa=id_empresa, data_inicio=inicio_anterior, data_fim=inicio_atual, **kwargs)