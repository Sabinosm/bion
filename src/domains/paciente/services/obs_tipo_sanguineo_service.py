"""obs_tipo_sanguineo_service.py

Regras de negócio do tipo sanguíneo do paciente, que é INSERT-ONLY: registrar
uma observação, ler a vigente e o histórico, e a distribuição estatística.

A leitura e a estatística exigem só o tenant (empresa). A escrita acontece sempre
DENTRO de um Atendimento em andamento do próprio profissional (checagem comum de
escrita clínica). Não há atualizar nem remover: corrigir é registrar uma nova
observação, que guarda quem registrou e o atendimento de origem. A vigente é a
mais recente, e registrar o mesmo valor que já é o vigente vale 409.

`commit=False` só faz flush (rota agregada do binário).
"""

from src.core.exceptions import ConflictoError
from ..repositories import PacienteRepository, ObservacaoTipoSanguineoRepository
from src.domains.paciente.schemas.schema_tipo_sanguineo import ObservacaoTipoSanguineoCreateSchema
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from .comum import validar_schema, paciente_ou_404, executar_com_rollback


class ObservacaoTipoSanguineoService:

    def __init__(self):
        self.repo = ObservacaoTipoSanguineoRepository()
        self._paciente_repo = PacienteRepository()
        self._ctx = ContextoClinicoService()

    # ------------------------------------------------------------ leitura
    def tipo_vigente(self, uuid_paciente: str, id_empresa: int):
        """Observação mais recente, ou None se nunca foi registrado."""
        p = paciente_ou_404(self._paciente_repo, uuid_paciente, id_empresa)
        return self.repo.find_mais_recente_por_paciente(p.id)

    def historico(self, uuid_paciente: str, id_empresa: int):
        """Todas as observações do paciente, da mais recente para a mais antiga."""
        p = paciente_ou_404(self._paciente_repo, uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    # ------------------------------------------------------------ escrita
    def registrar_tipo_sanguineo(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                                 autor: AutorClinico, commit: bool = True):
        """Registra uma nova observação de tipo sanguíneo no atendimento em andamento.

        Raises:
            DadosInvalidosError: corpo inválido (erros por campo).
            ConflictoError: o valor informado já é o vigente.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = validar_schema(ObservacaoTipoSanguineoCreateSchema, dados)

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
        return executar_com_rollback(self.repo, commit, lambda: self.repo.save(nova, commit=commit))

    # ------------------------------------------------------- estatísticas
    def distribuicao(self, id_empresa: int):
        """Distribuição de tipos sanguíneos na empresa, pela observação vigente de cada paciente."""
        return self.repo.distribuicao_tipo_sanguineo(id_empresa=id_empresa)
