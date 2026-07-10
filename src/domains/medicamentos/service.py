from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import CatalogoMedicamentosRepository


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

    def criar(self, dados: dict):
        from src.models.catalogos.catalogo_exames import CatalogoMedicamentos
        if not dados.get("principio_ativo"):
            raise DadosInvalidosError("principio_ativo é obrigatório.")
        m = CatalogoMedicamentos(
            principio_ativo=dados["principio_ativo"],
            classe_farmaceutica=dados.get("classe_farmaceutica"),
            nomes_comerciais_json=dados.get("nomes_comerciais"),
        )
        return self.repo.save(m)
