from .resultado_prescricao_repository import ResultadoPrescricaoRepository


class ResultadoPrescricaoService:
    def __init__(self):
        self.resultado_repo = ResultadoPrescricaoRepository()

    # --- C1: Doenças mais comuns por região ---
    def top_cid_por_regiao(self, id_empresa: int, dias: int = 14, limite: int = 10):
        return self.resultado_repo.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)

    # --- C3 (bônus): base para incidência por 100 mil ---
    def total_casos_por_regiao(self, id_empresa: int, dias: int = 14):
        return self.resultado_repo.total_casos_por_regiao(id_empresa=id_empresa, dias=dias)

    # --- C2: Evolução temporal de um CID específico ---
    def evolucao_cid(self, id_empresa: int, codigo_cid10: str, dias: int = 30):
        return self.resultado_repo.evolucao_cid(id_empresa=id_empresa, codigo_cid10=codigo_cid10, dias=dias)

    # --- C2 (comparação): evolução de 1 CID, com janela explícita ---
    def evolucao_cid_periodo(self, id_empresa: int, codigo_cid10: str, data_inicio, data_fim):
        return self.resultado_repo.evolucao_cid_periodo(
            id_empresa=id_empresa, codigo_cid10=codigo_cid10, data_inicio=data_inicio, data_fim=data_fim
        )