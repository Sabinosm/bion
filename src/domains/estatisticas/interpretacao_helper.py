"""
Helper compartilhado para o campo "interpretacao" nos retornos de
estatística. Usado pelas classes EstatisticasX -- não é chamado
diretamente pelas rotas.

Localização sugerida: src/domains/estatisticas/interpretacao.py
(ajustar conforme estrutura real do projeto)
"""

from datetime import datetime, timedelta, timezone

def nivel_por_percentual(valor: float) -> str:
    """Classifica um valor 0-100 em nivel, conforme thresholds definidos:
    85+ otimo, 70+ bom, 60+ ok, 50+ medio, 40+ medio_ruim, <40 ruim.

    Uso: métricas onde valor ALTO é bom (ex: taxa_conclusao, confianca_ia).
    Para métricas onde valor ALTO é ruim (ex: % de casos graves), usar
    nivel_por_percentual_invertido.
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
    """Mesmos thresholds de nivel_por_percentual, mas com a escala
    invertida -- para métricas onde valor ALTO é ruim (ex: % de reações
    alérgicas graves, % de abandono). Um valor de 5% aqui é "otimo",
    um valor de 90% é "ruim".
    """
    return nivel_por_percentual(100 - valor)


def interpretacao_percentual(valor: float, texto: str, direcao: str = "alto_bom", comparacao: str = None) -> dict:
    """Monta o dict de interpretação completo para métricas 0-100 com
    threshold conhecido (Grupo 1: taxa_conclusao, confianca_ia,
    completude_ia, gravidade %, etc).

    direcao: "alto_bom" (mais % é melhor, usa nivel_por_percentual) ou
    "alto_ruim" (mais % é pior, usa nivel_por_percentual_invertido --
    ex: % de casos graves, % de abandono).
    """
    nivel = nivel_por_percentual_invertido(valor) if direcao == "alto_ruim" else nivel_por_percentual(valor)
    return {
        "direcao": direcao,
        "texto": texto,
        "nivel": nivel,
        "comparacao": comparacao,
    }


def interpretacao_sem_nivel(texto: str, direcao: str = "neutro", comparacao: str = None) -> dict:
    """Monta o dict de interpretação para métricas do Grupo 2: volume/
    contagem sem threshold absoluto, mas onde direcao e/ou comparacao
    ainda agregam valor (ex: volume_atendimentos, tempo_medio_atendimento).

    nivel sempre None aqui -- não existe "85 atendimentos é ótimo",
    depende de contexto que o sistema não tem.
    """
    return {
        "direcao": direcao,
        "texto": texto,
        "nivel": None,
        "comparacao": comparacao,
    }


def calcular_comparacao(valor_atual: float, valor_anterior: float, unidade: str = "%") -> str:
    """Formata o texto de comparação padrão: 'Aumento/Queda de X% em
    comparação com o período anterior'. Retorna None se não houver
    base de comparação (valor_anterior None ou 0).
    """
    if valor_anterior is None or valor_anterior == 0 or valor_atual is None:
        return None

    variacao = round(((valor_atual - valor_anterior) / valor_anterior) * 100, 1)
    if variacao == 0:
        return "Sem variação em comparação com o período anterior"

    direcao_texto = "Aumento" if variacao > 0 else "Queda"
    return f"{direcao_texto} de {abs(variacao)}% em comparação com o período anterior"



def valor_periodo_anterior(metodo_periodo, id_empresa, dias, **kwargs):
    """Busca o valor do período anterior (mesma duração, sem
    sobreposição) usando o método de repository/service passado.
    Aceita kwargs extras para métodos que precisam de parâmetros
    além de id_empresa/data_inicio/data_fim (ex: codigo_cid10).
    """
    agora = datetime.now(timezone.utc)
    inicio_atual = agora - timedelta(days=dias)
    inicio_anterior = agora - timedelta(days=dias * 2)
    return metodo_periodo(id_empresa=id_empresa, data_inicio=inicio_anterior, data_fim=inicio_atual, **kwargs)