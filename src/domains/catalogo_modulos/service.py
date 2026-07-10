"""Regras de negócio da entidade CatalogoModulos."""

from src.core.exceptions import RecursoNaoEncontradoError
from .repository import CatalogoModulosRepository


class CatalogoModulosService:
    """Casos de uso de consulta ao catálogo de módulos de protocolo."""

    def __init__(self):
        self.repo = CatalogoModulosRepository()

    def buscar_por_uuid(self, uuid: str):
        """Retorna um CatalogoModulos pelo UUID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Módulo não encontrado: {uuid}")
        return e

    def listar(self):
        """Lista todos os CatalogoModulos cadastrados."""
        return self.repo.find_all()
