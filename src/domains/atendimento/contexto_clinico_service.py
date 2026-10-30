"""contexto_clinico_service.py

Checagem comum de ESCRITA clínica dentro de um Atendimento. Toda escrita de
dado clínico do paciente (alergia, reação, doença crônica, medicamento, tipo
sanguíneo, binário, conduta de enfermagem, dados da coleta) passa por aqui, para
que a regra viva num ponto só.

A checagem verifica, nesta ordem: que o Atendimento existe na empresa do
usuário (404 uniforme); que o paciente do caminho existe na empresa (404) e é o
mesmo do Atendimento (409 se for outro, para que a tela do paciente errado
falhe em vez de gravar no paciente errado); que quem escreve é o profissional
que abriu o Atendimento (403); que enfermeiro só escreve em triagem e médico em
qualquer tipo (403); que o Atendimento está em andamento (409); e que o
paciente pode receber atendimento, isto é, não tem óbito (409).

A permissão (403) vem antes do estado (409): quem não tem direito não descobre
em que estado o Atendimento está. O service nunca lê a sessão: o controller
monta o AutorClinico e o entrega.
"""

from dataclasses import dataclass

from src.core.exceptions import (
    RecursoNaoEncontradoError, ConflictoError, PermissaoNegadaError,
)
from src.domains.paciente.repositories import PacienteRepository
from src.domains.paciente.services.paciente_service import PacienteService


@dataclass(frozen=True)
class AutorClinico:
    """Quem está escrevendo, vindo da sessão (nunca do corpo da requisição)."""
    id_usuario: int
    funcao_clinica: str   # "medico" | "enfermeiro"
    id_empresa: int


@dataclass(frozen=True)
class ContextoClinico:
    """Atendimento e paciente já validados pela checagem de escrita."""
    atendimento: object
    paciente: object


class ContextoClinicoService:

    def __init__(self):
        self._paciente_repo = PacienteRepository()

    @staticmethod
    def _atendimento_repo():
        # import local: evita ciclo paciente <-> atendimento (mesmo padrão do ConsultaService)
        from src.domains.atendimento.repository import AtendimentoRepository
        return AtendimentoRepository()

    @staticmethod
    def _exigir_funcao_para_tipo(tipo_atendimento: str, funcao_clinica: str) -> None:
        """Médico escreve em qualquer tipo; enfermeiro só em triagem.

        Raises:
            PermissaoNegadaError: enfermeiro fora da triagem, ou função desconhecida.
        """
        if funcao_clinica == "medico":
            return
        if funcao_clinica == "enfermeiro" and tipo_atendimento == "triagem":
            return
        raise PermissaoNegadaError(
            "Enfermeiro só registra dados clínicos em atendimento de triagem."
        )

    def exigir_escrita(self, uuid_atendimento: str, uuid_paciente: str,
                       autor: AutorClinico) -> ContextoClinico:
        """Valida que `autor` pode escrever dado clínico no Atendimento e devolve o contexto.

        Raises:
            RecursoNaoEncontradoError: Atendimento ou paciente inexistente na empresa.
            ConflictoError: Atendimento de outro paciente; Atendimento fora de andamento;
                paciente sem condição de atendimento (óbito).
            PermissaoNegadaError: não é o dono do Atendimento; enfermeiro fora da triagem.
        """
        atendimento = self._atendimento_repo().find_by_uuid(uuid_atendimento, autor.id_empresa)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")

        if not self._paciente_repo.find_by_uuid(uuid_paciente, autor.id_empresa):
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        paciente = atendimento.consulta.paciente
        if paciente.uuid != uuid_paciente:
            raise ConflictoError("Este atendimento não é deste paciente.")

        if atendimento.realizado_por != autor.id_usuario:
            raise PermissaoNegadaError(
                "Só o profissional que abriu o atendimento pode registrar dados nele."
            )
        self._exigir_funcao_para_tipo(atendimento.tipo_atendimento, autor.funcao_clinica)

        if atendimento.status != "em-andamento":
            raise ConflictoError("O atendimento não está em andamento.")

        PacienteService.exigir_valido(paciente)
        return ContextoClinico(atendimento=atendimento, paciente=paciente)
