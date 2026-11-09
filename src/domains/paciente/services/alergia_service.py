"""alergia_service.py

Regras de negócio das alergias do paciente: adicionar, atualizar, remover e
restaurar, além da leitura e das estatísticas.

A leitura e as estatísticas exigem só o tenant (empresa). Toda escrita acontece
DENTRO de um Atendimento em andamento do próprio profissional, e a checagem
inteira vive na checagem comum de escrita clínica; o registro guarda quem
escreveu e em qual Atendimento (autor e atendimento de criação e de remoção). A
alergia nasce já com a primeira reação. A substância não é editável: só código e
confirmação mudam, e a mudança fica no log de auditoria da rota. Não pode haver
duas alergias ativas à mesma substância (a reação nova vai na existente); remover
é soft delete com motivo, e restaurar só vale se não houver outra ativa à mesma
substância.

`commit=False` só faz flush, usado pela rota de ação sensível e pela rota
agregada do binário, que compõem várias escritas atômicas.
"""

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from ..repositories import PacienteRepository, AlergiaRepository
from src.domains.paciente.schemas.schema_alergia import (
    AlergiaCreateSchema, AlergiaAtualizarSchema, AlergiaRemoverSchema,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from .comum import validar_schema, paciente_ou_404, executar_com_rollback


class AlergiaService:

    def __init__(self):
        self.repo = AlergiaRepository()
        self._paciente_repo = PacienteRepository()
        self._ctx = ContextoClinicoService()

    # ------------------------------------------------------------ helpers
    def _alergia_do_paciente(self, uuid_alergia: str, paciente, incluindo_deletados: bool = False):
        """Alergia do paciente pelo UUID. Raises: RecursoNaoEncontradoError (inexistente ou de outro paciente)."""
        busca = (self.repo.find_by_uuid_incluindo_deletados if incluindo_deletados
                 else self.repo.find_by_uuid)
        a = busca(uuid_alergia)
        if not a or a.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        return a

    # ------------------------------------------------------------ leitura
    def listar_alergias(self, uuid_paciente: str, id_empresa: int):
        """Alergias não removidas do paciente da empresa."""
        p = paciente_ou_404(self._paciente_repo, uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    # ------------------------------------------------------------ escrita
    def adicionar_alergia(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                          autor: AutorClinico, commit: bool = True):
        """Cria a alergia (já com a primeira reação) no atendimento em andamento.

        Raises:
            DadosInvalidosError: corpo inválido (erros por campo).
            ConflictoError: já existe alergia ativa à mesma substância.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = validar_schema(AlergiaCreateSchema, dados)

        if self.repo.find_ativa_por_substancia(ctx.paciente.id, entrada.substancia):
            raise ConflictoError(
                f"Já existe alergia ativa a '{entrada.substancia}' para este paciente. "
                "Registre uma nova reação nela em vez de duplicar."
            )

        nova = self._nova(ctx, entrada, autor)
        return executar_com_rollback(self.repo, commit, lambda: self.repo.save(nova, commit=commit))

    @staticmethod
    def _nova(ctx, entrada, autor):
        """Monta a Alergia com a primeira reação registrada. Só instancia; não persiste."""
        from src.models.pacientes import Alergia
        a = Alergia(
            id_paciente=ctx.paciente.id,
            substancia=entrada.substancia,
            codigo_substancia=entrada.codigo_substancia,
            flag_confirmado=entrada.flag_confirmado,
            criado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )
        a.registrar_reacao(
            manifestacao=entrada.tipo_reacao,
            gravidade=entrada.gravidade,
            descricao=entrada.descricao_reacao,
            criado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )
        return a

    def atualizar_alergia(self, uuid_atendimento: str, uuid_paciente: str, uuid_alergia: str,
                          dados: dict, autor: AutorClinico, commit: bool = True):
        """Atualiza codigo_substancia e flag_confirmado (a substância não é editável, ver
        AlergiaAtualizarSchema). A mudança fica no log de auditoria da rota.

        Raises:
            RecursoNaoEncontradoError: alergia inexistente ou de outro paciente.
            ConflictoError: alergia removida (restaure antes de editar).
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_do_paciente(uuid_alergia, ctx.paciente, incluindo_deletados=True)
        if alergia.deletado:
            raise ConflictoError(
                f"Alergia removida não pode ser atualizada: {uuid_alergia}. "
                "Restaure o registro antes de editar."
            )
        entrada = validar_schema(AlergiaAtualizarSchema, dados)
        for campo, valor in entrada.campos_informados().items():
            setattr(alergia, campo, valor)
        return executar_com_rollback(self.repo, commit, lambda: self.repo.save(alergia, commit=commit))

    def remover_alergia(self, uuid_atendimento: str, uuid_paciente: str, uuid_alergia: str,
                        dados: dict, autor: AutorClinico, commit: bool = True):
        """Soft delete com motivo, autor e atendimento. Remover de novo cai em 404 (a busca
        filtra deletado).

        Raises:
            RecursoNaoEncontradoError: alergia inexistente, de outro paciente ou já removida.
            DadosInvalidosError: motivo ausente ou inválido.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_do_paciente(uuid_alergia, ctx.paciente)
        entrada = validar_schema(AlergiaRemoverSchema, dados)
        executar_com_rollback(self.repo, commit, lambda: self.repo.soft_delete(
            alergia, entrada.motivo_delete, entrada.observacoes_delete,
            deletado_por=autor.id_usuario, id_atendimento_delecao=ctx.atendimento.id,
            commit=commit))
        return alergia

    def restaurar_alergia(self, uuid_atendimento: str, uuid_paciente: str, uuid_alergia: str,
                          autor: AutorClinico, commit: bool = True):
        """Reverte o soft delete.

        Raises:
            ConflictoError: a alergia não está removida, ou já existe outra ativa à mesma substância.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_do_paciente(uuid_alergia, ctx.paciente, incluindo_deletados=True)
        if not alergia.deletado:
            raise ConflictoError(f"Alergia não está removida, nada a restaurar: {uuid_alergia}")
        if self.repo.find_ativa_por_substancia(ctx.paciente.id, alergia.substancia):
            raise ConflictoError(
                f"Já existe alergia ativa a '{alergia.substancia}'; não é possível restaurar a removida."
            )
        return executar_com_rollback(self.repo, commit, lambda: self.repo.restaurar(alergia, commit=commit))

    # ------------------------------------------------------- estatísticas
    def top_substancias(self, id_empresa: int, limite: int = 10):
        """Substâncias mais reportadas na empresa (ver o repository)."""
        return self.repo.top_substancias(id_empresa=id_empresa, limite=limite)

    def gravidade_por_substancia(self, id_empresa: int, substancia: str):
        """Distribuição de gravidade das reações de uma substância."""
        return self.repo.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)

    def gravidade_geral(self, id_empresa: int):
        """Distribuição de gravidade das reações de todas as alergias da empresa."""
        return self.repo.gravidade_geral(id_empresa=id_empresa)
