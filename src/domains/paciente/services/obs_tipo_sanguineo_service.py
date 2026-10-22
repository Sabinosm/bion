from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, ObservacaoTipoSanguineoRepository
from src.domains.paciente.schemas.schema_tipo_sanguineo import (
    ObservacaoTipoSanguineoCreateSchema, erros_pydantic_por_campo,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico


class ObservacaoTipoSanguineoService:
    """Tipo sanguíneo do paciente (insert-only).

    LEITURA (tipo_vigente, historico, distribuicao): só tenant (id_empresa).

    ESCRITA (registrar): sempre DENTRO de um Atendimento `em-andamento` do
    próprio profissional -- a checagem vive em
    ContextoClinicoService.exigir_escrita. Não há atualizar/remover:
    corrigir é registrar uma nova observação. A observação guarda quem
    registrou e o Atendimento de origem.

    `commit=False` só faz flush (rota agregada do binário).
    """

    def __init__(self):
        self.repo = ObservacaoTipoSanguineoRepository()
        self._paciente_repo = PacienteRepository()
        self._ctx = ContextoClinicoService()

    # ------------------------------------------------------------ helpers
    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    @staticmethod
    def _validar(schema, dados: dict):
        try:
            return schema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

    def _executar(self, commit: bool, fn):
        try:
            return fn()
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    # ------------------------------------------------------------ leitura
    def tipo_vigente(self, uuid_paciente: str, id_empresa: int):
        """Observação mais recente, ou None se nunca foi registrado."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_mais_recente_por_paciente(p.id)

    def historico(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    # ------------------------------------------------------------ escrita
    def registrar_tipo_sanguineo(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                                 autor: AutorClinico, commit: bool = True):
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = self._validar(ObservacaoTipoSanguineoCreateSchema, dados)

        vigente = self.repo.find_mais_recente_por_paciente(ctx.paciente.id)
        if vigente and vigente.tipo_sanguineo == entrada.tipo_sanguineo:
            raise ConflictoError(
                f"'{entrada.tipo_sanguineo}' já é o tipo sanguíneo vigente deste paciente."
            )

        from src.models.pacientes import ObservacaoTipoSanguineo
        nova = ObservacaoTipoSanguineo(
            id_paciente=ctx.paciente.id,
            tipo_sanguineo=entrada.tipo_sanguineo,
            registrado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )
        return self._executar(commit, lambda: self.repo.save(nova, commit=commit))

    # ------------------------------------------------------- estatísticas
    def distribuicao(self, id_empresa: int):
        return self.repo.distribuicao_tipo_sanguineo(id_empresa=id_empresa)