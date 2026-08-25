from src.domains.prescricao.service import PrescricaoService

p_svc = PrescricaoService()


class EstatisticasPrescricao:

    # --- D4: Medicamentos mais prescritos por classe farmacêutica ---
    def top_por_classe(self, id_empresa, dias=30, limite=10):
        """Retorna: {"ranking": [...], "leitura": str}"""
        ranking = p_svc.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)

        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = f"{principal['classe_farmaceutica']} é a classe mais prescrita ({principal['total']} prescrições)"

        return {"ranking": ranking, "leitura": leitura}

    # --- D4 (detalhe): princípios ativos dentro de 1 classe ---
    def top_principios_ativos_por_classe(self, id_empresa, classe, dias=30, limite=10):
        """Retorna: {"classe": str, "ranking": [...], "leitura": str}"""
        ranking = p_svc.top_principios_ativos_por_classe(
            id_empresa=id_empresa, classe=classe, dias=dias, limite=limite
        )

        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = f"Dentro de {classe}, {principal['principio_ativo']} é o mais prescrito ({principal['total']} vezes)"

        return {"classe": classe, "ranking": ranking, "leitura": leitura}