from src.core.exceptions import RecursoNaoEncontradoError
from .repository import CatalogoMedicamentosRepository
from .interacoes.interacoes_medicamento_repository import InteracoesMedicamentosRepository


class CatalogoMedicamentosService:

    def __init__(self):
        self.repo = CatalogoMedicamentosRepository()
        self.repo_interacoes = InteracoesMedicamentosRepository()

    def buscar_por_uuid(self, uuid: str):
        m = self.repo.find_by_uuid(uuid)
        if not m:
            raise RecursoNaoEncontradoError(f"Medicamento não encontrado: {uuid}")
        return m

    def listar(self):
        return self.repo.find_all()

    def listar_paginado(self, termo, pagina: int, por_pagina: int):
        return self.repo.listar_paginado(termo, pagina, por_pagina)

    def buscar(self, termo: str):
        return self.repo.buscar_por_principio_ativo(termo)

    def verificar_interacoes(self, uuid: str) -> dict:
        """Interações cadastradas para o medicamento + total da base.

        O total acompanha o resultado para que quem consome (médico,
        IA) consiga distinguir "sem interação cadastrada" de "base
        ainda vazia/parcial" -- lista vazia sozinha não prova ausência
        de interação clínica."""
        m = self.buscar_por_uuid(uuid)
        return {
            "interacoes": self.repo_interacoes.find_por_medicamento(m.id),
            "total_na_base": self.repo_interacoes.contar(),
        }

