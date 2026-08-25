from src.domains.atendimento.service import AtendimentoService

ats = AtendimentoService()


def _formatar_duracao(segundos: float) -> str:
    """Converte segundos em 'XminYs' pro texto de leitura."""
    minutos, seg = divmod(int(segundos), 60)
    return f"{minutos}min{seg:02d}s"
 
 
class EstatisticasAtendimento:
 
    # --- A2: Tempo médio de atendimento por tipo ---
    def tempo_medio_por_tipo(self, id_empresa, dias=30):
        """Duração média por tipo_atendimento (triagem, avaliacao-medica, etc).
 
        Retorna: {"por_tipo": [{"tipo_atendimento", "media_segundos",
                  "media_formatada", "total"}, ...], "leitura": str}
 
        Nota: variação % vs. período anterior (mencionada na leitura do
        .md) fica pendente -- precisaria de uma segunda chamada com
        dias*2 e comparar as duas janelas. Deixei de fora por ora pra
        não assumir a regra de "período anterior" sem confirmar com
        vocês (dias anteriores consecutivos? mesmo período do mês
        passado?).
        """
        bruto = ats.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)
 
        por_tipo = [
            {
                **item,
                "media_formatada": _formatar_duracao(item["media_segundos"]),
            }
            for item in bruto
        ]
 
        leitura = None
        if por_tipo:
            principal = max(por_tipo, key=lambda item: item["total"])
            leitura = (
                f"Tempo médio de atendimento ({principal['tipo_atendimento']}): "
                f"{principal['media_formatada']}"
            )
 
        return {"por_tipo": por_tipo, "leitura": leitura}
 
    # --- E2: Tendência de eficiência acumulada ---
    def tendencia_eficiencia(self, id_empresa, dias=30):
        """Compara o tempo médio de atendimento em dois períodos
        CONSECUTIVOS e EXCLUSIVOS de `dias` dias cada (ex: dias=30 ->
        "últimos 30 dias" vs. "os 30 dias antes desses") -- corrigido
        para não sobrepor janelas (versão anterior comparava 'últimos 60'
        com 'últimos 30', que se sobrepunham e distorciam a variação %).
 
        Retorna: {"periodo_atual": [...], "periodo_anterior": [...],
                  "variacao_percentual": float|None, "leitura": str}
        """
        from datetime import datetime, timedelta, timezone
 
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
 
        variacao = None
        leitura = None
        if media_atual is not None and media_anterior:
            variacao = round(((media_atual - media_anterior) / media_anterior) * 100, 1)
            direcao = "mais rápida" if variacao < 0 else "mais lenta"
            leitura = (
                f"A equipe está {abs(variacao)}% {direcao} nos últimos {dias} dias, "
                f"comparado aos {dias} dias anteriores"
            )
        elif media_atual is not None and media_anterior is None:
            leitura = "Sem dados suficientes no período anterior para comparação"
 
        return {
            "periodo_atual": periodo_atual,
            "periodo_anterior": periodo_anterior,
            "variacao_percentual": variacao,
            "leitura": leitura,
        }
 