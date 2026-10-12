from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repositories import AlergiaRepository, ReacaoAlergiaRepository
from src.domains.paciente.schemas.schema_alergia import (
    ReacaoAlergiaCreateSchema, AlergiaRemoverSchema, erros_pydantic_por_campo,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico


class ReacaoAlergiaService:
    """Reações de uma alergia (histórico de ocorrências).

    Escrita sempre dentro de um Atendimento em andamento do próprio
    profissional (ContextoClinicoService); a reação guarda autor e
    Atendimento de origem, e a remoção é soft delete com motivo."""

    def __init__(self):
        self.repo = ReacaoAlergiaRepository()
        self._alergia_repo = AlergiaRepository()
        self._ctx = ContextoClinicoService()

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
                self._alergia_repo.rollback()
            raise

    def adicionar_reacao(self, uuid_atendimento: str, uuid_paciente: str, uuid_alergia: str,
                         dados: dict, autor: AutorClinico, commit: bool = True):
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_repo.find_by_uuid(uuid_alergia)
        if not alergia or alergia.id_paciente != ctx.paciente.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        entrada = self._validar(ReacaoAlergiaCreateSchema, dados)

        alergia.registrar_reacao(
            manifestacao=entrada.manifestacao,
            gravidade=entrada.gravidade,
            descricao=entrada.descricao,
            data_ocorrencia=entrada.data_ocorrencia,
            criado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )
        return self._executar(commit, lambda: self._alergia_repo.save(alergia, commit=commit))

    def remover_reacao(self, uuid_atendimento: str, uuid_paciente: str, uuid_reacao: str,
                       dados: dict, autor: AutorClinico, commit: bool = True):
        """Soft delete de UMA reação (registrada por engano); a alergia e as
        demais reações ficam intactas. Alergia-mãe removida => 404."""
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        reacao = self.repo.find_by_uuid(uuid_reacao)
        if (not reacao or reacao.alergia.deletado
                or reacao.alergia.id_paciente != ctx.paciente.id):
            raise RecursoNaoEncontradoError(f"Reação não encontrada: {uuid_reacao}")
        entrada = self._validar(AlergiaRemoverSchema, dados)
        self._executar(commit, lambda: self.repo.soft_delete(
            reacao, entrada.motivo_delete, entrada.observacoes_delete,
            deletado_por=autor.id_usuario, id_atendimento_delecao=ctx.atendimento.id,
            commit=commit))
        return reacao