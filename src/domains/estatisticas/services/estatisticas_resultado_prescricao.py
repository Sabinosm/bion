from src.domains.prescricao.service import PrescricaoService
from src.models.corp.regiao_geografica import RegiaoGeografica

ps = PrescricaoService()


class EstatisticasResultadoPrescricao:

    # --- C1: Doenças mais comuns por região ---
    def top_cid_por_regiao(self, id_empresa, dias=14, limite=10):
        """Ranking de CID10 por região.

        Retorna: {"ranking": [...], "leitura": str}
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

        return {"ranking": ranking, "leitura": leitura}

    # --- C3 (bônus): incidência por 100 mil habitantes ---
    def incidencia_por_regiao(self, id_empresa, dias=14):
        """Casos totais por região, normalizados pela população estimada.

        Retorna: {"ranking": [{"regiao", "total_casos", "populacao_estimada",
                  "incidencia_por_100mil"}, ...], "leitura": str}

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

        # ordena pelas que têm incidência calculável, maior primeiro;
        # as sem população vão pro fim, sem quebrar o sort
        ranking.sort(key=lambda x: (x["incidencia_por_100mil"] is None, -(x["incidencia_por_100mil"] or 0)))

        leitura = None
        if ranking and ranking[0]["incidencia_por_100mil"] is not None:
            principal = ranking[0]
            leitura = (
                f"Incidência: {principal['incidencia_por_100mil']} casos por 100 mil habitantes "
                f"na {principal['regiao']} -- a maior entre as regiões monitoradas"
            )

        return {"ranking": ranking, "leitura": leitura}