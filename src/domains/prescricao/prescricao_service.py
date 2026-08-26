from .prescricao_repository import PrescricaoRepository


class PrescricaoService:
    def __init__(self):
        self.prescricao_repo = PrescricaoRepository()

    # --- D4: Medicamentos mais prescritos por classe ---
    def top_por_classe(self, id_empresa: int, dias: int = 30, limite: int = 10):
        return self.prescricao_repo.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)

    def top_principios_ativos_por_classe(self, id_empresa: int, classe: str, dias: int = 30, limite: int = 10):
        return self.prescricao_repo.top_principios_ativos_por_classe(
            id_empresa=id_empresa, classe=classe, dias=dias, limite=limite
        )