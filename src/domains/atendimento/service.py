"""Regras de negócio do ciclo de vida do Atendimento (abertura e finalização)."""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from .repository import AtendimentoRepository
from src.domains.consulta.repository import ConsultaRepository


class AtendimentoService:
    """Casos de uso relacionados à abertura, consulta e finalização de Atendimentos."""

    def __init__(self):
        self.repo = AtendimentoRepository()
        self.consulta_repo = ConsultaRepository()

    def buscar_por_uuid(self, uuid: str):
        """Retorna um Atendimento pelo UUID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid}")
        return e

    def listar(self):
        """Lista todos os Atendimentos cadastrados."""
        return self.repo.find_all()

    def listar_por_consulta(self, uuid_consulta: str):
        """Lista os Atendimentos vinculados a uma Consulta."""
        c = self.consulta_repo.find_by_uuid(uuid_consulta)
        if not c:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")
        return self.repo.find_por_consulta(c.id)

    def abrir_triagem(self, uuid_consulta: str, id_usuario: int):
        """
        Abre um Atendimento do tipo triagem para a Consulta e atualiza
        seu status para 'em-triagem'.

        Raises:
            RecursoNaoEncontradoError: se a Consulta não existir.
        """
        from src.models.clinico import Atendimento
        c = self.consulta_repo.find_by_uuid(uuid_consulta)
        if not c:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")

        atendimento = Atendimento(
            id_consulta=c.id,
            tipo_atendimento="triagem",
            realizado_por=id_usuario,
            status="em-andamento",
            data_hora_inicio=datetime.now(timezone.utc),
        )
        self.repo.save(atendimento)

        c.status_consulta = "em-triagem"
        self.consulta_repo.save(c)
        return atendimento

    def abrir_avaliacao_medica(self, uuid_consulta: str, id_usuario: int):
        """
        Abre um Atendimento do tipo avaliação médica para a Consulta e
        atualiza seu status para 'em-atendimento'.

        Raises:
            RecursoNaoEncontradoError: se a Consulta não existir.
        """
        from src.models.clinico import Atendimento
        c = self.consulta_repo.find_by_uuid(uuid_consulta)
        if not c:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")

        atendimento = Atendimento(
            id_consulta=c.id,
            tipo_atendimento="avaliacao-medica",
            realizado_por=id_usuario,
            status="em-andamento",
            data_hora_inicio=datetime.now(timezone.utc),
        )
        self.repo.save(atendimento)

        c.status_consulta = "em-atendimento"
        self.consulta_repo.save(c)
        return atendimento

    def finalizar(self, uuid_atendimento: str, observacoes: str = None):
        """
        Finaliza um Atendimento em andamento, registrando data/hora de
        término e observações opcionais do profissional.

        Raises:
            ConflictoError: se o Atendimento já estiver finalizado.
        """
        atendimento = self.buscar_por_uuid(uuid_atendimento)
        if atendimento.status == "finalizado":
            raise ConflictoError("Atendimento já está finalizado.")
        atendimento.status = "finalizado"
        atendimento.data_hora_fim = datetime.now(timezone.utc)
        if observacoes:
            atendimento.observacoes_profissional = observacoes
        return self.repo.save(atendimento)
