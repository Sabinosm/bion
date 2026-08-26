from src.domains.estatisticas.interpretacao_helper import interpretacao_sem_nivel
from src.domains.prescricao.prescricao_service import PrescricaoService

p_svc = PrescricaoService()


class EstatisticasPrescricao:
 
    # --- D4: Medicamentos mais prescritos por classe farmacêutica ---
    def top_por_classe(self, id_empresa, dias=30, limite=10):
        """Grupo 2 -- ranking, sem nivel/comparacao: é um top N que
        naturalmente muda de composição a cada consulta (winner-take-all),
        comparar com o período anterior item a item vira ruído.
 
        Retorna: {"ranking": [...], "leitura": str, "interpretacao": {...}}
        """
        ranking = p_svc.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)
 
        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = f"{principal['classe_farmaceutica']} é a classe mais prescrita ({principal['total']} prescrições)"
 
        interpretacao = interpretacao_sem_nivel(
            texto="Ranking informativo -- concentração muito alta numa única classe pode sinalizar sazonalidade (ex: surto) ou merece checagem de protocolo, mas não há um perfil 'certo' fixo",
            direcao="neutro",
            comparacao=None,
        )
 
        return {"ranking": ranking, "leitura": leitura, "interpretacao": interpretacao}
 
    # --- D4 (detalhe): princípios ativos dentro de 1 classe ---
    def top_principios_ativos_por_classe(self, id_empresa, classe, dias=30, limite=10):
        """Grupo 3 -- drill-down informativo, sem interpretação (é
        detalhamento do D4 acima, a leitura de "bom/ruim" já fica na
        rota principal).
 
        Retorna: {"classe": str, "ranking": [...], "leitura": str}
        """
        ranking = p_svc.top_principios_ativos_por_classe(
            id_empresa=id_empresa, classe=classe, dias=dias, limite=limite
        )
 
        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = f"Dentro de {classe}, {principal['principio_ativo']} é o mais prescrito ({principal['total']} vezes)"
 
        return {"classe": classe, "ranking": ranking, "leitura": leitura}