from datetime import datetime, timedelta, timezone

from src.domains.atendimento.service import AtendimentoService
from src.domains.estatisticas.interpretacao_helper import calcular_comparacao, interpretacao_sem_nivel

ats = AtendimentoService()


def _formatar_duracao(segundos: float) -> str:
    """Converte segundos em 'XminYs' pro texto de leitura."""
    minutos, seg = divmod(int(segundos), 60)
    return f"{minutos}min{seg:02d}s"
 
 
class EstatisticasAtendimento:
 
    # --- A2: Tempo médio de atendimento por tipo ---
    def tempo_medio_por_tipo(self, id_empresa, dias=30):
        """Duração média por tipo_atendimento (triagem, avaliacao-medica, etc).
 
        Grupo 2 -- sem nivel (o que é "rápido" varia por tipo de
        atendimento, não tem threshold universal), mas direcao=alto_ruim
        (menor tempo é melhor) + comparacao com o período anterior.
 
        Retorna: {"por_tipo": [{"tipo_atendimento", "media_segundos",
                  "media_formatada", "total"}, ...], "leitura": str,
                  "interpretacao": {...}|None}
        """
        bruto = ats.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)
 
        por_tipo = [
            {**item, "media_formatada": _formatar_duracao(item["media_segundos"])}
            for item in bruto
        ]
 
        if not por_tipo:
            return {"por_tipo": por_tipo, "leitura": None, "interpretacao": None}
 
        # média geral ponderada, para a comparação de período (não por tipo)
        def media_geral(lista):
            total_seg = sum(item["media_segundos"] * item["total"] for item in lista)
            total_n = sum(item["total"] for item in lista)
            return (total_seg / total_n) if total_n else None
 
        media_atual = media_geral(por_tipo)
 
        agora = datetime.now(timezone.utc)
        inicio_atual = agora - timedelta(days=dias)
        inicio_anterior = agora - timedelta(days=dias * 2)
        bruto_anterior = ats.tempo_medio_por_tipo_periodo(
            id_empresa=id_empresa, data_inicio=inicio_anterior, data_fim=inicio_atual
        )
        media_anterior = media_geral(bruto_anterior)
 
        principal = max(por_tipo, key=lambda item: item["total"])
        leitura = f"Tempo médio de atendimento ({principal['tipo_atendimento']}): {principal['media_formatada']}"
 
        interpretacao = interpretacao_sem_nivel(
            texto="Quanto menor o tempo, melhor -- indica agilidade no fluxo. O tempo 'ideal' varia por tipo de atendimento, então avalie a tendência, não um valor fixo",
            direcao="alto_ruim",
            comparacao=calcular_comparacao(media_atual, media_anterior, unidade="s"),
        )
 
        return {"por_tipo": por_tipo, "leitura": leitura, "interpretacao": interpretacao}
 
    # --- E2: Tendência de eficiência acumulada ---
    def tendencia_eficiencia(self, id_empresa, dias=30):
        """Compara o tempo médio de atendimento em dois períodos
        CONSECUTIVOS e EXCLUSIVOS de `dias` dias cada.
 
        Caso especial -- esta rota JÁ É a comparação (não faz sentido
        comparar a comparação com um "período anterior" dela mesma).
        nivel fica None (variação %, sem threshold absoluto tipo
        "85% otimo"); direcao e o texto de comparacao vêm da própria
        variação calculada.
 
        Retorna: {"periodo_atual": [...], "periodo_anterior": [...],
                  "variacao_percentual": float|None, "leitura": str,
                  "interpretacao": {...}|None}
        """
        agora = datetime.now(timezone.utc)
        inicio_atual = agora - timedelta(days=dias)
        inicio_anterior = agora - timedelta(days=dias * 2)
 
        periodo_atual = ats.tempo_medio_por_tipo_periodo(
            id_empresa=id_empresa, data_inicio=inicio_atual, data_fim=agora
        )
        periodo_anterior = ats.tempo_medio_por_tipo_periodo(
            id_empresa=id_empresa, data_inicio=inicio_anterior, data_fim=inicio_atual
        )
 
        def media_geral(lista):
            total_seg = sum(item["media_segundos"] * item["total"] for item in lista)
            total_n = sum(item["total"] for item in lista)
            return (total_seg / total_n) if total_n else None
 
        media_atual = media_geral(periodo_atual)
        media_anterior = media_geral(periodo_anterior)
 
        if media_atual is None:
            return {
                "periodo_atual": periodo_atual, "periodo_anterior": periodo_anterior,
                "variacao_percentual": None, "leitura": None, "interpretacao": None,
            }
 
        if not media_anterior:
            return {
                "periodo_atual": periodo_atual, "periodo_anterior": periodo_anterior,
                "variacao_percentual": None,
                "leitura": "Sem dados suficientes no período anterior para comparação",
                "interpretacao": None,
            }
 
        variacao = round(((media_atual - media_anterior) / media_anterior) * 100, 1)
        direcao_texto = "mais rápida" if variacao < 0 else "mais lenta"
        leitura = (
            f"A equipe está {abs(variacao)}% {direcao_texto} nos últimos {dias} dias, "
            f"comparado aos {dias} dias anteriores"
        )
 
        interpretacao = interpretacao_sem_nivel(
            texto="Queda no tempo médio indica ganho de eficiência; alta sustentada pode indicar sobrecarga da equipe ou casos mais complexos",
            direcao="alto_ruim",
            comparacao=calcular_comparacao(media_atual, media_anterior, unidade="s"),
        )
 
        return {
            "periodo_atual": periodo_atual,
            "periodo_anterior": periodo_anterior,
            "variacao_percentual": variacao,
            "leitura": leitura,
            "interpretacao": interpretacao,
        }