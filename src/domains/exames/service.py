from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import CatalogoExamesRepository

TIPOS_VALIDOS = ("laboratorial", "imagem", "funcional", "outro")


class CatalogoExamesService:

    def __init__(self):
        self.repo = CatalogoExamesRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Exame não encontrado: {uuid}")
        return e

    def listar(self):
        return self.repo.find_all()

    def buscar(self, termo: str):
        return self.repo.buscar_por_nome(termo)

    def listar_paginado(self, termo, tipo, pagina: int, por_pagina: int):
        """Busca do médico: exames ativos, por nome (pt/en) ou sinônimo, com filtro opcional de tipo."""
        if tipo and tipo not in TIPOS_VALIDOS:
            raise DadosInvalidosError(f"tipo inválido: use {', '.join(TIPOS_VALIDOS)}.")
        return self.repo.listar_paginado(termo, tipo, pagina, por_pagina)

    def criar(self, dados: dict):
        from src.models.catalogos.catalogo_exames import CatalogoExames
        if not dados.get("nome_exame"):
            raise DadosInvalidosError("nome_exame é obrigatório.")
        e = CatalogoExames(
            nome_exame=dados["nome_exame"],
            codigo_tuss=dados.get("codigo_tuss"),
            tipo=dados.get("tipo"),
            material=dados.get("material"),
            jejum_horas=dados.get("jejum_horas"),
            observacoes=dados.get("observacoes"),
        )
        return self.repo.save(e)


