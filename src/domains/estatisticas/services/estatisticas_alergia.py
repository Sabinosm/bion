from src.domains.paciente.services import DadosClinicosService

dcs = DadosClinicosService()

class EstatisticasAlergia:

    # --- D2: Alergias mais reportadas ---
    def top_substancias(self, id_empresa, limite=10):
        """Ranking de substâncias alergênicas mais reportadas.

        Retorna: {"ranking": [{"substancia", "total"}, ...], "leitura": str}
        """
        ranking = dcs.top_substancias(id_empresa=id_empresa, limite=limite)

        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = (
                f"{principal['substancia']} foi a substância alérgena mais reportada "
                f"({principal['total']} casos)"
            )

        return {"ranking": ranking, "leitura": leitura}

    # --- D2 (detalhe): drill-down de gravidade por substância ---
    def gravidade_por_substancia(self, id_empresa, substancia):
        """Distribuição de gravidade das reações para 1 substância.

        Retorna: {"substancia": str, "por_gravidade": {...}, "leitura": str}
        """
        por_gravidade = dcs.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
        total = sum(por_gravidade.values())
        graves = por_gravidade.get("grave", 0)

        leitura = None
        if total:
            pct_graves = round((graves / total) * 100, 1)
            leitura = f"{pct_graves}% das reações a {substancia} foram classificadas como graves"

        return {"substancia": substancia, "por_gravidade": por_gravidade, "leitura": leitura}

    # --- F4: Gravidade geral das reações alérgicas (sem filtro por substância) ---
    def gravidade_geral(self, id_empresa):
        """Retorna: {"por_gravidade": {...}, "leitura": str}"""
        por_gravidade = dcs.gravidade_geral(id_empresa=id_empresa)
        total = sum(por_gravidade.values())
        graves = por_gravidade.get("grave", 0)

        leitura = None
        if total:
            pct = round((graves / total) * 100, 1)
            leitura = f"{pct}% de todas as reações alérgicas registradas foram classificadas como graves"

        return {"por_gravidade": por_gravidade, "leitura": leitura}

    # --- D2: Alergias mais reportadas ---
    def top_substancias(self, id_empresa, limite=10):
        """Ranking de substâncias alergênicas mais reportadas.

        Retorna: {"ranking": [{"substancia", "total"}, ...], "leitura": str}
        """
        ranking = dcs.top_substancias(id_empresa=id_empresa, limite=limite)

        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = (
                f"{principal['substancia']} foi a substância alérgena mais reportada "
                f"({principal['total']} casos)"
            )

        return {"ranking": ranking, "leitura": leitura}

    # --- D2 (detalhe): drill-down de gravidade por substância ---
    def gravidade_por_substancia(self, id_empresa, substancia):
        """Distribuição de gravidade das reações para 1 substância.

        Retorna: {"substancia": str, "por_gravidade": {...}, "leitura": str}
        """
        por_gravidade = dcs.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
        total = sum(por_gravidade.values())
        graves = por_gravidade.get("grave", 0)

        leitura = None
        if total:
            pct_graves = round((graves / total) * 100, 1)
            leitura = f"{pct_graves}% das reações a {substancia} foram classificadas como graves"

        return {"substancia": substancia, "por_gravidade": por_gravidade, "leitura": leitura}