from datetime import datetime, timedelta, timezone
from ..interpretacao_helper import interpretacao_percentual, calcular_comparacao
from src.domains.consulta.service import ConsultaService

cs = ConsultaService()

# status_consulta que conta como "concluído" para efeito de A3.
# 'encerrada' é o único status terminal "positivo" no enum de Consulta;
# os demais (aguardando-*, em-*) são em andamento, não abandono.
_STATUS_CONCLUIDO = "encerrada"
 
 
class EstatisticasConsulta:
 
    def consultas_hoje(self, id_empresa):
        return cs.contar_consultas_dia(id_empresa=id_empresa)
 
    # --- A1: Volume de atendimentos ---
    def volume_por_dia(self, id_empresa, dias=30):
        """Série diária de consultas iniciadas, para gráfico de linha/barra.
 
        Grupo 2 -- sem interpretação estruturada. Volume absoluto não
        tem "certo/errado" sem contexto de demanda; fica só o "leitura"
        textual, como já estava.
 
        Retorna: {"serie": [{"data": ..., "total": ...}, ...], "total_periodo": int}
        """
        serie = cs.consultas_por_dia(id_empresa=id_empresa, dias=dias)
        total_periodo = sum(item["total"] for item in serie)
        return {
            "serie": serie,
            "total_periodo": total_periodo,
            "leitura": f"Foram realizados {total_periodo} atendimentos nos últimos {dias} dias",
        }
 
    # --- A3: Taxa de conclusão vs. abandono ---
    def taxa_conclusao(self, id_empresa, dias=30):
        """Percentual de consultas que chegaram a status 'encerrada'.
 
        Grupo 1 -- % com threshold conhecido, ganha interpretacao completa
        (nivel + direcao + comparacao com o período anterior).
 
        Retorna: {"percentual": float, "total": int, "concluidas": int,
                  "por_status": {status: total, ...}, "leitura": str,
                  "interpretacao": {...}}
        """
        por_status = cs.consultas_por_status(id_empresa=id_empresa, dias=dias)
        total = sum(por_status.values())
        concluidas = por_status.get(_STATUS_CONCLUIDO, 0)
        percentual = round((concluidas / total) * 100, 1) if total else 0.0
 
        # período anterior, mesma duração, sem sobreposição
        agora = datetime.now(timezone.utc)
        inicio_atual = agora - timedelta(days=dias)
        inicio_anterior = agora - timedelta(days=dias * 2)
        por_status_anterior = cs.consultas_por_status_periodo(
            id_empresa=id_empresa, data_inicio=inicio_anterior, data_fim=inicio_atual
        )
        total_anterior = sum(por_status_anterior.values())
        concluidas_anterior = por_status_anterior.get(_STATUS_CONCLUIDO, 0)
        percentual_anterior = round((concluidas_anterior / total_anterior) * 100, 1) if total_anterior else None
 
        interpretacao = interpretacao_percentual(
            valor=percentual,
            texto="Alto = fluxo saudável de atendimento; baixo = investigar em qual etapa os pacientes estão travando ou abandonando",
            direcao="alto_bom",
            comparacao=calcular_comparacao(percentual, percentual_anterior),
        )
 
        return {
            "percentual": percentual,
            "total": total,
            "concluidas": concluidas,
            "por_status": por_status,
            "leitura": f"{percentual}% dos atendimentos iniciados foram concluídos",
            "interpretacao": interpretacao,
        }
        