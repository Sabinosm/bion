from .interacoes_medicamento_repository import InteracoesMedicamentosRepository

class InteracoesMedicamentosService:

        def __init__(self):
            self.repo = InteracoesMedicamentosRepository()

        # --- D1: Interações medicamentosas cadastradas por gravidade ---
        def contar_por_gravidade(self):
            return self.repo.contar_por_gravidade()