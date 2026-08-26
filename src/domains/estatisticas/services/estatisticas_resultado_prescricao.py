from datetime import datetime, timedelta, timezone

from src.domains.estatisticas.interpretacao_helper import calcular_comparacao, interpretacao_sem_nivel
from src.domains.prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from src.models.corp.regiao_geografica import RegiaoGeografica

ps = ResultadoPrescricaoService()


class EstatisticasResultadoPrescricao:
 
    # --- C1: Doenças mais comuns por região ---
    def top_cid_por_regiao(self, id_empresa, dias=14, limite=10):
        """Ranking de CID10 por região.
 
        Grupo 2 -- sem nivel/comparacao: é multi-dimensional (CID x
        região), comparar cada par com o período anterior geraria uma
        matriz grande demais para ser útil num campo simples.
 
        Retorna: {"ranking": [...], "leitura": str, "interpretacao": {...}}
        """
        ranking = ps.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)
 
        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = (
                f"{principal['total']} pacientes diagnosticados com "
                f"{principal['descricao_cid10']} ({principal['codigo_cid10']}) "
                f"na região {principal['regiao']} nos últimos {dias} dias"
            )
 
        interpretacao = interpretacao_sem_nivel(
            texto="Concentração alta de um CID numa região pode sinalizar surto ou fator ambiental local -- vale cruzar com C2 (evolução temporal) para confirmar tendência antes de agir",
            direcao="neutro",
            comparacao=None,
        )
 
        return {"ranking": ranking, "leitura": leitura, "interpretacao": interpretacao}
 
    # --- C3 (bônus): incidência por 100 mil habitantes ---
    def incidencia_por_regiao(self, id_empresa, dias=14):
        """Casos totais por região, normalizados pela população estimada.
 
        Grupo 2 -- sem nivel (incidência "normal" varia por doença/CID,
        não dá pra cravar threshold) nem comparacao (ranking multi-região,
        mesmo caso de C1).
 
        Retorna: {"ranking": [...], "leitura": str, "interpretacao": {...}}
 
        Regiões sem populacao_estimada cadastrada ficam com
        incidencia_por_100mil=None (não dá pra assumir 0, seria enganoso).
        """
        casos_por_regiao = ps.total_casos_por_regiao(id_empresa=id_empresa, dias=dias)
 
        ranking = []
        for item in casos_por_regiao:
            regiao = RegiaoGeografica.query.get(item["id_regiao"])
            populacao = regiao.populacao_estimada if regiao else None
 
            incidencia = None
            if populacao:
                incidencia = round((item["total"] / populacao) * 100_000, 1)
 
            ranking.append({
                "regiao": item["regiao"],
                "total_casos": item["total"],
                "populacao_estimada": populacao,
                "incidencia_por_100mil": incidencia,
            })
 
        ranking.sort(key=lambda x: (x["incidencia_por_100mil"] is None, -(x["incidencia_por_100mil"] or 0)))
 
        leitura = None
        if ranking and ranking[0]["incidencia_por_100mil"] is not None:
            principal = ranking[0]
            leitura = (
                f"Incidência: {principal['incidencia_por_100mil']} casos por 100 mil habitantes "
                f"na {principal['regiao']} -- a maior entre as regiões monitoradas"
            )
 
        interpretacao = interpretacao_sem_nivel(
            texto="Incidência 'esperada' varia por tipo de agravo -- use como ranking comparativo entre regiões, não como valor absoluto de bom/ruim",
            direcao="neutro",
            comparacao=None,
        )
 
        return {"ranking": ranking, "leitura": leitura, "interpretacao": interpretacao}
 
    # --- C2: Evolução temporal de um CID específico ---
    def evolucao_cid(self, id_empresa, codigo_cid10, dias=30):
        """Grupo 2 -- ESTE ganha comparacao de verdade: é o caso de uso
        clássico de vigilância epidemiológica, subiu ou caiu o número
        de casos de 1 CID específico vs. o período anterior. direcao
        neutro porque "mais casos" não é universalmente ruim (pode ser
        melhora de sub-notificação, campanha de rastreio, etc) -- mas
        na prática, para a maioria dos CIDs de vigilância, um aumento
        acentuado costuma ser motivo de atenção.
 
        Retorna: {"codigo_cid10": str, "serie": [...], "total_periodo": int,
                  "leitura": str, "interpretacao": {...}}
        """
        serie = ps.evolucao_cid(id_empresa=id_empresa, codigo_cid10=codigo_cid10, dias=dias)
        total = sum(item["total"] for item in serie)
 
        agora = datetime.now(timezone.utc)
        inicio_atual = agora - timedelta(days=dias)
        inicio_anterior = agora - timedelta(days=dias * 2)
        serie_anterior = ps.evolucao_cid_periodo(
            id_empresa=id_empresa, codigo_cid10=codigo_cid10, data_inicio=inicio_anterior, data_fim=inicio_atual
        )
        total_anterior = sum(item["total"] for item in serie_anterior)
 
        leitura = f"{total} casos de {codigo_cid10} registrados nos últimos {dias} dias" if total else \
            f"Nenhum caso de {codigo_cid10} registrado nos últimos {dias} dias"
 
        interpretacao = interpretacao_sem_nivel(
            texto="Aumento acentuado no número de casos merece investigação -- pode indicar surto; queda pode indicar melhora ou sub-notificação, avalie o contexto",
            direcao="neutro",
            comparacao=calcular_comparacao(total, total_anterior, unidade=""),
        )
 
        return {
            "codigo_cid10": codigo_cid10,
            "serie": serie,
            "total_periodo": total,
            "leitura": leitura,
            "interpretacao": interpretacao,
        }
 