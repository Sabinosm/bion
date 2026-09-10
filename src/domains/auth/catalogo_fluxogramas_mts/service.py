"""Regras de negócio da entidade CatalogoFluxogramasMts."""

from src.core.exceptions import RecursoNaoEncontradoError
from .repository import CatalogoFluxogramasMtsRepository


class CatalogoFluxogramasMtsService:
    """Casos de uso de consulta ao catálogo de fluxogramas do protocolo MTS."""

    def __init__(self):
        self.repo = CatalogoFluxogramasMtsRepository()

    def buscar_por_uuid(self, uuid: str):
        """Retorna um CatalogoFluxogramasMts pelo UUID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Fluxograma MTS não encontrado: {uuid}")
        return e

    def listar(self):
        """Lista todos os CatalogoFluxogramasMts cadastrados."""
        return self.repo.find_all()
