from src.core.exceptions import RecursoNaoEncontradoError
from .prescricao_exame_repository import PrescricaoExameRepository


class PrescricaoExameService:
    def __init__(self):
        self.repo = PrescricaoExameRepository()

    # --- D3: Urgência de exames -- IA vs. profissional ---
    def urgencia_por_origem(self, id_empresa: int, dias: int = 30):
        return self.repo.urgencia_por_origem(id_empresa=id_empresa, dias=dias)
    
    def adicionar_exame(self, uuid_resultado: str, dados: dict):
        """
        Adiciona um exame prescrito a um ResultadoPrescricao.

        Raises:
            RecursoNaoEncontradoError: se o ResultadoPrescricao não existir.
        """
        from src.models.clinico import PrescricaoExame
        resultado = self.repo.find_by_uuid(uuid_resultado)
        if not resultado:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")

        pe = PrescricaoExame(
            id_resultado=resultado.id,
            id_exame=dados.get("id_exame"),
            urgencia=dados.get("urgencia", "rotina"),
            justificativa=dados.get("justificativa"),
            origem_sugestao=dados.get("origem_sugestao", "medico"),
            id_output_origem=dados.get("id_output_origem"),
        )
        return self.repo.save(pe)