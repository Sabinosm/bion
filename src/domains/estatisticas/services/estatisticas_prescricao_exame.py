from src.domains.prescricao.service import PrescricaoService

ps = PrescricaoService()


class EstatisticasPrescricaoExame:

    # --- D3: Urgência de exames -- IA vs. profissional ---
    def urgencia_por_origem(self, id_empresa, dias=30):
        """Cruzamento urgencia x origem_sugestao, com % de participação
        da IA em cada nível de urgência.

        Retorna: {"matriz": [...], "percentual_urgente_por_origem": {...}, "leitura": str}
        """
        bruto = ps.urgencia_por_origem(id_empresa=id_empresa, dias=dias)

        # soma por urgência, pra calcular % de cada origem dentro dela
        total_por_urgencia = {}
        for item in bruto:
            total_por_urgencia[item["urgencia"]] = total_por_urgencia.get(item["urgencia"], 0) + item["total"]

        matriz = [
            {
                **item,
                "percentual": round((item["total"] / total_por_urgencia[item["urgencia"]]) * 100, 1)
                if total_por_urgencia[item["urgencia"]] else 0.0,
            }
            for item in bruto
        ]

        # leitura focada em "urgente", que é o caso de maior interesse clínico
        urgentes = [item for item in matriz if item["urgencia"] == "urgente"]
        leitura = None
        if urgentes:
            partes = [f"{item['percentual']}% pela {item['origem_sugestao']}" for item in urgentes]
            leitura = f"Exames marcados como urgentes: {', '.join(partes)}"

        return {"matriz": matriz, "leitura": leitura}