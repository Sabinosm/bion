"""
estatisticas_atendimento.py

Estatísticas de tempo de atendimento: duração média por tipo, tendência de
eficiência entre dois períodos consecutivos e tempo médio entre o início dos
sintomas e o atendimento. As métricas de duração não têm nível (o que é
"rápido" varia por tipo), só direção (menor é melhor) e comparação com o
período anterior. Quando a base mistura, em proporção relevante, consultas em
que o mesmo profissional faz triagem e avaliação com consultas em que as
etapas são de profissionais diferentes, a média combinada vem acompanhada de
um aviso com o detalhamento por grupo.
"""

from datetime import datetime, timedelta, timezone

from src.domains.atendimento.service import AtendimentoService
from src.domains.estatisticas.interpretacao_helper import calcular_comparacao, interpretacao_sem_nivel, valor_periodo_anterior

_atendimento_svc = AtendimentoService()

# A partir de que fração das consultas segmentáveis (mesmo_profissional
# + transferencia) sendo "mesmo_profissional" a média combinada de A2/E2
# passa a misturar dois comportamentos distintos o suficiente para
# merecer aviso. Sem isso, tempo_medio_por_tipo mostra um número só que
# não representa nem clínicas com enfermeiro dedicado nem clínicas onde
# o médico faz tudo sozinho.
_LIMIAR_ALERTA_MESMO_PROFISSIONAL = 0.3


def _formatar_duracao(segundos: float) -> str:
    """Converte segundos em 'XminYs' pro texto de leitura."""
    minutos, seg = divmod(int(segundos), 60)
    return f"{minutos}min{seg:02d}s"


def _media_ponderada(lista: list):
    """Média geral de segundos ponderada pelo total de cada tipo, ou None se não há atendimentos."""
    total_seg = sum(item["media_segundos"] * item["total"] for item in lista)
    total_n = sum(item["total"] for item in lista)
    return (total_seg / total_n) if total_n else None


def _aviso_mistura_profissional(id_empresa, dias):
    """
    Verifica se a base de Consultas do período mistura, em proporção
    relevante, casos "mesmo profissional fez triagem e avaliação" com
    casos "profissionais diferentes". Se sim, retorna um dict com o
    detalhamento por grupo pra exibir como aviso; senão, None.

    Isso não substitui tempo_medio_por_tipo -- é um complemento
    opcional, mostrado só quando a mistura é grande o bastante pra
    distorcer a leitura da média combinada.
    """
    segmentado = _atendimento_svc.tempo_medio_por_tipo_segmentado(id_empresa=id_empresa, dias=dias)
    if not segmentado:
        return None

    total_mesmo = sum(i["total"] for i in segmentado if i["grupo"] == "mesmo_profissional")
    total_transferencia = sum(i["total"] for i in segmentado if i["grupo"] == "transferencia")
    total_classificavel = total_mesmo + total_transferencia

    if total_classificavel == 0:
        return None

    proporcao_mesmo = total_mesmo / total_classificavel
    if proporcao_mesmo < _LIMIAR_ALERTA_MESMO_PROFISSIONAL:
        return None

    por_grupo = {}
    for item in segmentado:
        por_grupo.setdefault(item["grupo"], []).append({
            "tipo_atendimento": item["tipo_atendimento"],
            "media_segundos": item["media_segundos"],
            "media_formatada": _formatar_duracao(item["media_segundos"]),
            "total": item["total"],
        })

    return {
        "proporcao_mesmo_profissional": round(proporcao_mesmo * 100, 1),
        "por_grupo": por_grupo,
        "leitura": (
            f"{round(proporcao_mesmo * 100, 1)}% das consultas no período tiveram o mesmo "
            "profissional fazendo triagem e avaliação médica. O tempo médio combinado acima "
            "mistura esse comportamento com o de fluxos onde as etapas são feitas por "
            "profissionais diferentes -- considere olhar os grupos separadamente."
        ),
    }


class EstatisticasAtendimento:

    def tempo_medio_por_tipo(self, id_empresa, dias=30):
        """Duração média por tipo_atendimento (triagem, avaliacao-medica,
        etc.), com tendência vs. período anterior (A2).

        Sem `nivel`: o que é "rápido" varia por tipo de atendimento, não
        tem threshold universal — só direção (menor tempo é melhor) e
        comparação.

        Inclui "aviso_mistura_profissional": None, ou um dict com a
        quebra por grupo (mesmo_profissional vs. transferencia) quando
        a mistura é grande o bastante pra distorcer a leitura da média
        combinada — ver `_aviso_mistura_profissional`.

        Retorna: {"por_tipo": [{"tipo_atendimento", "media_segundos",
                  "media_formatada", "total"}, ...], "leitura": str,
                  "interpretacao": {...}|None,
                  "aviso_mistura_profissional": {...}|None}
        """
        bruto = _atendimento_svc.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)

        por_tipo = [
            {**item, "media_formatada": _formatar_duracao(item["media_segundos"])}
            for item in bruto
        ]

        if not por_tipo:
            return {
                "por_tipo": por_tipo, "leitura": None, "interpretacao": None,
                "aviso_mistura_profissional": None,
            }

        media_atual = _media_ponderada(por_tipo)

        bruto_anterior = valor_periodo_anterior(_atendimento_svc.tempo_medio_por_tipo_periodo, id_empresa, dias)
        media_anterior = _media_ponderada(bruto_anterior)

        principal = max(por_tipo, key=lambda item: item["total"])
        leitura = f"Tempo médio de atendimento ({principal['tipo_atendimento']}): {principal['media_formatada']}"

        interpretacao = interpretacao_sem_nivel(
            texto="Quanto menor o tempo, melhor -- indica agilidade no fluxo. O tempo 'ideal' varia por tipo de atendimento, então avalie a tendência, não um valor fixo",
            direcao="alto_ruim",
            comparacao=calcular_comparacao(media_atual, media_anterior, unidade="s"),
        )

        return {
            "por_tipo": por_tipo,
            "leitura": leitura,
            "interpretacao": interpretacao,
            "aviso_mistura_profissional": _aviso_mistura_profissional(id_empresa, dias),
        }

    def tendencia_eficiencia(self, id_empresa, dias=30):
        """Compara o tempo médio de atendimento em dois períodos
        consecutivos e exclusivos de `dias` dias cada (E2).

        Caso especial: esta rota já é a própria comparação, então não
        há "período anterior" dela mesma. `nivel` fica None (é variação
        %, sem threshold absoluto tipo "85% ótimo").

        Retorna: {"periodo_atual": [...], "periodo_anterior": [...],
                  "variacao_percentual": float|None, "leitura": str,
                  "interpretacao": {...}|None}
        """
        agora = datetime.now(timezone.utc)
        inicio_atual = agora - timedelta(days=dias)

        periodo_atual = _atendimento_svc.tempo_medio_por_tipo_periodo(
            id_empresa=id_empresa, data_inicio=inicio_atual, data_fim=agora
        )
        periodo_anterior = valor_periodo_anterior(_atendimento_svc.tempo_medio_por_tipo_periodo, id_empresa, dias)

        media_atual = _media_ponderada(periodo_atual)
        media_anterior = _media_ponderada(periodo_anterior)

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
        if variacao == 0:
            leitura = f"Sem variação no tempo de atendimento nos últimos {dias} dias, comparado aos {dias} dias anteriores"
        else:
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

    def tempo_ate_atendimento(self, id_empresa, dias=30):
        """Tempo médio entre início dos sintomas e atendimento (C4).

        Retorna: {"media_horas": float|None, "leitura": str}
        """
        media = _atendimento_svc.media_horas_ate_atendimento(id_empresa=id_empresa, dias=dias)

        leitura = None
        if media is not None:
            if media < 24:
                leitura = f"Pacientes buscam atendimento em média {round(media, 1)}h após início dos sintomas"
            else:
                dias_media = round(media / 24, 1)
                leitura = f"Pacientes buscam atendimento em média {dias_media} dias após início dos sintomas"

        return {"media_horas": round(media, 1) if media is not None else None, "leitura": leitura}