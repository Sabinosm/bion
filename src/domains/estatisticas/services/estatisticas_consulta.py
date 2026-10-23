"""
estatisticas_consulta.py

Estatísticas de consultas: contagem do dia, série diária de volume e taxa de
conclusão. O volume não tem nível (o certo depende da capacidade da equipe),
só comparação com o período anterior. A taxa de conclusão considera apenas
consultas encerradas, separando as concluídas das abandonadas (evasão), e é um
percentual com interpretação completa: nível, direção (mais é melhor) e
comparação com o período anterior.
"""

from src.domains.estatisticas.interpretacao_helper import interpretacao_percentual, calcular_comparacao, interpretacao_sem_nivel, valor_periodo_anterior
from src.domains.consulta.service import ConsultaService

_consulta_svc = ConsultaService()

# Desfecho final (de uma consulta 'encerrada') que conta como abandono em A3.
# Evasão não é um status: é um desfecho_final. Os demais desfechos (alta,
# internacao, transferencia, obito) e a ausência de desfecho contam como
# concluída. Consultas ainda em andamento não entram na taxa.
_DESFECHO_ABANDONO = "evasao"


def _percentual(parte, total, vazio=None):
    """Percentual de `parte` sobre `total` (uma casa decimal); `vazio` se total é 0."""
    return round((parte / total) * 100, 1) if total else vazio


def _concluidas_e_abandonadas(por_desfecho: dict) -> tuple:
    """(concluidas, abandonadas) a partir da contagem de consultas encerradas por desfecho."""
    abandonadas = por_desfecho.get(_DESFECHO_ABANDONO, 0)
    concluidas = sum(por_desfecho.values()) - abandonadas
    return concluidas, abandonadas


class EstatisticasConsulta:

    def consultas_hoje(self, id_empresa):
        return _consulta_svc.contar_consultas_hoje(id_empresa=id_empresa)

    def volume_por_dia(self, id_empresa, dias=30):
        """Série diária de consultas iniciadas, para gráfico de linha/barra (A1).

        Sem `nivel`: volume "certo" depende da capacidade da equipe, sem
        threshold universal. `direcao` neutra, com comparação vs. período
        anterior.

        Retorna: {"serie": [...], "total_periodo": int, "leitura": str, "interpretacao": {...}}
        """
        serie = _consulta_svc.consultas_por_dia(id_empresa=id_empresa, dias=dias)
        total_periodo = sum(item["total"] for item in serie)

        serie_anterior = valor_periodo_anterior(_consulta_svc.consultas_por_dia_periodo, id_empresa, dias)
        total_anterior = sum(item["total"] for item in serie_anterior)

        interpretacao = interpretacao_sem_nivel(
            texto="Volume alto ou baixo não é bom nem ruim isoladamente -- avalie junto com o efetivo disponível (A4) e o tempo médio de atendimento (A2) para saber se a equipe está sobrecarregada",
            direcao="neutro",
            comparacao=calcular_comparacao(total_periodo, total_anterior, unidade=""),
        )

        return {
            "serie": serie,
            "total_periodo": total_periodo,
            "leitura": f"Foram realizados {total_periodo} atendimentos nos últimos {dias} dias",
            "interpretacao": interpretacao,
        }

    def taxa_conclusao(self, id_empresa, dias=30):
        """Percentual de consultas encerradas que foram concluídas, sem
        evasão (A3), com interpretação completa (nível + direção +
        comparação com o período anterior).

        Só entram consultas 'encerrada': concluída é a encerrada sem
        desfecho 'evasao'; abandonada é a encerrada com desfecho 'evasao'.
        Consultas em andamento não contam. `total` = concluídas + abandonadas.

        Retorna: {"percentual": float, "total": int, "concluidas": int,
                  "abandonadas": int, "por_desfecho": {desfecho: total, ...},
                  "por_status": {status: total, ...}, "leitura": str,
                  "interpretacao": {...}}
        """
        por_desfecho = _consulta_svc.consultas_por_desfecho(id_empresa=id_empresa, dias=dias)
        concluidas, abandonadas = _concluidas_e_abandonadas(por_desfecho)
        total = concluidas + abandonadas
        percentual = _percentual(concluidas, total, vazio=0.0)

        # período anterior, mesma duração, sem sobreposição
        por_desfecho_anterior = valor_periodo_anterior(_consulta_svc.consultas_por_desfecho_periodo, id_empresa, dias)
        concluidas_anterior, abandonadas_anterior = _concluidas_e_abandonadas(por_desfecho_anterior)
        percentual_anterior = _percentual(concluidas_anterior, concluidas_anterior + abandonadas_anterior)

        interpretacao = interpretacao_percentual(
            valor=percentual,
            texto="Alto = poucos pacientes abandonam o fluxo antes de concluir o atendimento; baixo = investigar em qual etapa (triagem, espera) os pacientes estão desistindo",
            direcao="alto_bom",
            comparacao=calcular_comparacao(percentual, percentual_anterior),
        )

        return {
            "percentual": percentual,
            "total": total,
            "concluidas": concluidas,
            "abandonadas": abandonadas,
            "por_desfecho": por_desfecho,
            "por_status": _consulta_svc.consultas_por_status(id_empresa=id_empresa, dias=dias),
            "leitura": f"{percentual}% das consultas encerradas foram concluídas, sem evasão ({abandonadas} evasões no período)",
            "interpretacao": interpretacao,
        }