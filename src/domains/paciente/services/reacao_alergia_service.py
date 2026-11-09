"""reacao_alergia_service.py

Regras de negócio das reações de uma alergia (o histórico de ocorrências):
adicionar uma reação a uma alergia existente e remover uma reação registrada por
engano.

A escrita acontece sempre dentro de um Atendimento em andamento do próprio
profissional (checagem comum de escrita clínica); a reação guarda o autor e o
atendimento de origem, e a remoção é soft delete com motivo, sem afetar a
alergia nem as demais reações. Alergia removida (ou de outro paciente) vale 404.
"""

from src.core.exceptions import RecursoNaoEncontradoError
from ..repositories import AlergiaRepository, ReacaoAlergiaRepository
from src.domains.paciente.schemas.schema_alergia import ReacaoAlergiaCreateSchema, AlergiaRemoverSchema
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from .comum import validar_schema, executar_com_rollback


class ReacaoAlergiaService:

    def __init__(self):
        self.repo = ReacaoAlergiaRepository()
        self._alergia_repo = AlergiaRepository()
        self._ctx = ContextoClinicoService()

    def adicionar_reacao(self, uuid_atendimento: str, uuid_paciente: str, uuid_alergia: str,
                         dados: dict, autor: AutorClinico, commit: bool = True):
        """Registra uma nova reação numa alergia do paciente. Devolve a alergia atualizada.

        Raises:
            RecursoNaoEncontradoError: alergia inexistente, removida ou de outro paciente.
            DadosInvalidosError: corpo inválido (erros por campo).
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_repo.find_by_uuid(uuid_alergia)
        if not alergia or alergia.id_paciente != ctx.paciente.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        entrada = validar_schema(ReacaoAlergiaCreateSchema, dados)

        alergia.registrar_reacao(
            manifestacao=entrada.manifestacao,
            gravidade=entrada.gravidade,
            descricao=entrada.descricao,
            data_ocorrencia=entrada.data_ocorrencia,
            criado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )
        return executar_com_rollback(
            self._alergia_repo, commit, lambda: self._alergia_repo.save(alergia, commit=commit))

    def remover_reacao(self, uuid_atendimento: str, uuid_paciente: str, uuid_reacao: str,
                       dados: dict, autor: AutorClinico, commit: bool = True):
        """Soft delete de UMA reação (registrada por engano); a alergia e as demais reações ficam
        intactas.

        Raises:
            RecursoNaoEncontradoError: reação inexistente, de alergia removida ou de outro paciente.
            DadosInvalidosError: motivo ausente ou inválido.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        reacao = self.repo.find_by_uuid(uuid_reacao)
        if (not reacao or reacao.alergia.deletado
                or reacao.alergia.id_paciente != ctx.paciente.id):
            raise RecursoNaoEncontradoError(f"Reação não encontrada: {uuid_reacao}")
        entrada = validar_schema(AlergiaRemoverSchema, dados)
        executar_com_rollback(self._alergia_repo, commit, lambda: self.repo.soft_delete(
            reacao, entrada.motivo_delete, entrada.observacoes_delete,
            deletado_por=autor.id_usuario, id_atendimento_delecao=ctx.atendimento.id,
            commit=commit))
        return reacao
