from src.core.exceptions import RecursoNaoEncontradoError
from .indicacao_terapeutica_repository import IndicacaoTerapeuticaRepository


class IndicacaoTerapeuticaService:

    def __init__(self):
        self.repo = IndicacaoTerapeuticaRepository()

    def listar(self):
        return self.repo.find_all()

    def buscar_por_uuid(self, uuid: str):
        i = self.repo.find_by_uuid(uuid)
        if not i:
            raise RecursoNaoEncontradoError(f"Indicação terapêutica não encontrada: {uuid}")
        return i

    def buscar_por_nome(self, termo: str):
        """Sentido sintoma -> indicação. Usado pelo médico digitando
        livre (ex: 'dor de cabeça') e pela IA para reconhecer menção a
        sintoma em texto."""
        return self.repo.buscar_por_nome(termo)

    def medicamentos_da_indicacao(self, uuid: str):
        """Sentido sintoma -> medicamentos, já resolvendo o uuid
        público para o id interno."""
        indicacao = self.buscar_por_uuid(uuid)
        return self.repo.medicamentos_da_indicacao(indicacao.id)