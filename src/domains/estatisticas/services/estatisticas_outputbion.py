from datetime import datetime, timedelta, timezone

from src.domains.protocolos_ia.service import OutputBionService
from src.domains.estatisticas.interpretacao_helper import interpretacao_percentual, calcular_comparacao

ob_svc = OutputBionService()


def _media_periodo_anterior(metodo_periodo, id_empresa, dias):
    """Helper local: busca a média do período anterior (mesma duração,
    sem sobreposição) usando o método de repository/service passado.
    """
    agora = datetime.now(timezone.utc)
    inicio_atual = agora - timedelta(days=dias)
    inicio_anterior = agora - timedelta(days=dias * 2)
    return metodo_periodo(id_empresa=id_empresa, data_inicio=inicio_anterior, data_fim=inicio_atual)
 
 
class EstatisticasOutputBion:
 
    # --- B1: Confiança média da IA ---
    def confianca_media(self, id_empresa, dias=30):
        """Grupo 1 -- % com threshold conhecido: interpretacao completa.
 
        Retorna: {"media": float|None, "dias": int, "leitura": str, "interpretacao": {...}|None}
        """
        media = ob_svc.media_confianca(id_empresa=id_empresa, dias=dias)
 
        if media is None:
            return {"media": None, "dias": dias, "leitura": "Sem execuções da IA no período", "interpretacao": None}
 
        media_anterior = _media_periodo_anterior(ob_svc.media_confianca_periodo, id_empresa, dias)
 
        interpretacao = interpretacao_percentual(
            valor=media,
            texto="Alto = IA decidindo com segurança; baixo = revisar qualidade dos dados de entrada ou performance do modelo",
            direcao="alto_bom",
            comparacao=calcular_comparacao(media, media_anterior),
        )
 
        return {
            "media": round(media, 2),
            "dias": dias,
            "leitura": f"Confiança média da IA nos últimos {dias} dias: {round(media, 1)}%",
            "interpretacao": interpretacao,
        }
 
    # --- B2: Completude média dos dados de entrada ---
    def completude_media(self, id_empresa, dias=30):
        """Grupo 1 -- % com threshold conhecido: interpretacao completa.
 
        Retorna: {"media": float|None, "dias": int, "leitura": str, "interpretacao": {...}|None}
        """
        media = ob_svc.media_completude(id_empresa=id_empresa, dias=dias)
 
        if media is None:
            return {"media": None, "dias": dias, "leitura": "Sem execuções da IA no período", "interpretacao": None}
 
        media_anterior = _media_periodo_anterior(ob_svc.media_completude_periodo, id_empresa, dias)
 
        interpretacao = interpretacao_percentual(
            valor=media,
            texto="Alto = profissionais preenchendo os dados de entrada de forma completa; baixo = triagem apressada ou campos obrigatórios sendo pulados",
            direcao="alto_bom",
            comparacao=calcular_comparacao(media, media_anterior),
        )
 
        return {
            "media": round(media, 2),
            "dias": dias,
            "leitura": f"Completude média dos dados de entrada: {round(media, 1)}%",
            "interpretacao": interpretacao,
        }
 
    # --- B4: Versão do modelo de IA em uso ---
    def versoes_em_uso(self, id_empresa, dias=30):
        """Grupo 3 -- sem interpretação (informativo/rastreabilidade,
        não tem lado bom/ruim uma versão específica estar em uso)."""
        versoes = ob_svc.versoes_em_uso(id_empresa=id_empresa, dias=dias)
 
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
 
    # --- E3: Correlação completude x confiança ---
    def correlacao_completude_confianca(self, id_empresa, dias=30):
        """Caso especial -- coeficiente de Pearson vai de -1 a 1, não é
        uma escala 0-100, então não usa nivel_por_percentual. direcao
        aqui é sempre 'neutro': correlação alta não é 'boa' nem 'ruim'
        por si só, é só informação de quão ligadas as duas métricas estão.
 
        Retorna: {"coeficiente": float|None, "n_amostras": int, "leitura": str, "interpretacao": {...}|None}
        """
        pares = ob_svc.pares_completude_confianca(id_empresa=id_empresa, dias=dias)
 
        n = len(pares)
        if n < 2:
            return {"coeficiente": None, "n_amostras": n, "leitura": "Amostra insuficiente para calcular correlação", "interpretacao": None}
 
        xs = [p[0] for p in pares]
        ys = [p[1] for p in pares]
        media_x = sum(xs) / n
        media_y = sum(ys) / n
 
        cov = sum((x - media_x) * (y - media_y) for x, y in pares)
        var_x = sum((x - media_x) ** 2 for x in xs)
        var_y = sum((y - media_y) ** 2 for y in ys)
 
        if var_x == 0 or var_y == 0:
            return {"coeficiente": None, "n_amostras": n, "leitura": "Sem variação suficiente nos dados para calcular correlação", "interpretacao": None}
 
        coeficiente = round(cov / (var_x ** 0.5 * var_y ** 0.5), 3)
 
        if coeficiente >= 0.7:
            forca = "forte"
        elif coeficiente >= 0.4:
            forca = "moderada"
        elif coeficiente >= 0.1:
            forca = "fraca"
        else:
            forca = "praticamente nula"
 
        leitura = f"Correlação {forca} entre completude e confiança (r={coeficiente}, n={n})"
 
        interpretacao = {
            "direcao": "neutro",
            "texto": "Correlação forte sugere que melhorar a completude dos dados de entrada tende a elevar a confiança da IA -- não indica causalidade, só associação",
            "nivel": None,
            "comparacao": None,
        }
 
        return {"coeficiente": coeficiente, "n_amostras": n, "leitura": leitura, "interpretacao": interpretacao}