from src.core.exceptions import RecursoNaoEncontradoError
from .contraindicacao_repository import ContraindicacaoRepository


class ContraindicacaoService:

    def __init__(self):
        self.repo = ContraindicacaoRepository()

    def listar(self):
        return self.repo.find_all()

    def buscar_por_uuid(self, uuid: str):
        c = self.repo.find_by_uuid(uuid)
        if not c:
            raise RecursoNaoEncontradoError(f"Contraindicação não encontrada: {uuid}")
        return c

    def buscar_por_nome(self, termo: str):
        return self.repo.buscar_por_nome(termo)

    def medicamentos_da_contraindicacao(self, uuid: str):
        """Sentido condição -> medicamentos, já resolvendo o uuid
        público para o id interno. Útil para o médico ver, por
        exemplo, todos os medicamentos contraindicados em gravidez."""
        contraindicacao = self.buscar_por_uuid(uuid)
        return self.repo.medicamentos_da_contraindicacao(contraindicacao.id)