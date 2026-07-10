"""Regras de negócio da entidade Consulta."""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from .repository import ConsultaRepository

DESFECHOS_VALIDOS = ("alta", "internacao", "transferencia", "obito", "evasao")


class ConsultaService:
    """Casos de uso relacionados à abertura, consulta e encerramento de Consultas."""

    def __init__(self):
        self.repo = ConsultaRepository()

    def buscar_por_uuid(self, uuid: str):
        """Retorna uma Consulta pelo UUID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid}")
        return e

    def listar(self, apenas_abertas: bool = False):
        """Lista Consultas. Se apenas_abertas=True, filtra as não encerradas."""
        if apenas_abertas:
            return self.repo.find_abertas()
        return self.repo.find_all()

    def listar_por_paciente(self, id_paciente: int):
        """Lista o histórico de Consultas de um paciente específico."""
        return self.repo.find_por_paciente(id_paciente)

    def abrir(self, uuid_paciente: str, dados: dict, id_usuario: int):
        """
        Abre uma nova Consulta para um paciente existente.

        Args:
            uuid_paciente: UUID público do paciente.
            dados: payload com tipo_consulta e origem_encaminhamento (opcionais).
            id_usuario: ID de quem está iniciando a consulta.

        Raises:
            RecursoNaoEncontradoError: se o paciente não existir.
        """
        from src.models.clinico import Consulta
        from src.domains.paciente.repositories import PacienteRepository

        paciente = PacienteRepository().find_by_uuid(uuid_paciente)
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")

        c = Consulta(
            id_paciente=paciente.id,
            tipo_consulta=dados.get("tipo_consulta", "triagem"),
            origem_encaminhamento=dados.get("origem_encaminhamento", "espontanea"),
            status_consulta="aguardando-triagem",
            data_hora_inicio=datetime.now(timezone.utc),
            iniciada_por=id_usuario,
        )
        return self.repo.save(c)

    def encerrar(self, uuid: str, desfecho: str, id_usuario: int):
        """
        Encerra uma Consulta em aberto com um desfecho final.

        Args:
            uuid: UUID da Consulta.
            desfecho: um de DESFECHOS_VALIDOS.
            id_usuario: ID de quem está encerrando.

        Raises:
            ConflictoError: se a Consulta já estiver encerrada.
            DadosInvalidosError: se o desfecho informado for inválido.
        """
        c = self.buscar_por_uuid(uuid)
        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta já está encerrada.")
        if desfecho not in DESFECHOS_VALIDOS:
            raise DadosInvalidosError(
                f"Desfecho inválido. Use um de: {', '.join(DESFECHOS_VALIDOS)}"
            )

        c.status_consulta = "encerrada"
        c.desfecho_final = desfecho
        c.data_hora_fim = datetime.now(timezone.utc)
        c.finalizada_por = id_usuario
        return self.repo.save(c)
