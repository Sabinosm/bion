from src.core.exceptions import RecursoNaoEncontradoError
from .repository import CatalogoMedicamentosRepository, InteracoesMedicamentosRepository


class CatalogoMedicamentosService:

    def __init__(self):
        self.repo = CatalogoMedicamentosRepository()

    def buscar_por_uuid(self, uuid: str):
        m = self.repo.find_by_uuid(uuid)
        if not m:
            raise RecursoNaoEncontradoError(f"Medicamento não encontrado: {uuid}")
        return m

    def listar(self):
        return self.repo.find_all()

    def buscar(self, termo: str):
        return self.repo.buscar_por_principio_ativo(termo)

    def verificar_interacoes(self, uuid: str):
        m = self.buscar_por_uuid(uuid)
        return self.repo.interacoes_de(m.id)



class InteracoesMedicamentosService:
    
    def __init__(self):
        self.repo = InteracoesMedicamentosRepository()

    # --- D1: Interações medicamentosas cadastradas por gravidade ---
    def contar_por_gravidade(self):
        return self.repo.contar_por_gravidade()