from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, AlergiaRepository
from src.domains.paciente.schemas.schema_alergia import (
    AlergiaCreateSchema, AlergiaAtualizarSchema, AlergiaRemoverSchema, erros_pydantic_por_campo,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico


class AlergiaService:
    """Alergias do paciente.

    LEITURA (listar_*, estatísticas): só tenant (id_empresa).

    ESCRITA (adicionar/atualizar/remover/restaurar): sempre DENTRO de um
    Atendimento `em-andamento` do próprio profissional -- a checagem
    inteira vive em ContextoClinicoService.exigir_escrita. O registro
    guarda quem escreveu e em qual Atendimento (criado_por /
    id_atendimento_origem; deletado_por / id_atendimento_delecao).

    `commit=False` só faz flush: usado pela rota acao_sensivel e pela
    rota agregada do binário, que compõem várias escritas atômicas.
    """

    def __init__(self):
        self.repo = AlergiaRepository()
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

    def _alergia_do_paciente(self, uuid_alergia: str, paciente, incluindo_deletados: bool = False):
        busca = (self.repo.find_by_uuid_incluindo_deletados if incluindo_deletados
                 else self.repo.find_by_uuid)
        a = busca(uuid_alergia)
        if not a or a.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        return a

    def _executar(self, commit: bool, fn):
        """Se este service é dono do commit, desfaz tudo em caso de falha."""
        try:
            return fn()
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    # ------------------------------------------------------------ leitura
    def listar_alergias(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    # ------------------------------------------------------------ escrita
    def adicionar_alergia(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                          autor: AutorClinico, commit: bool = True):
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = self._validar(AlergiaCreateSchema, dados)

        if self.repo.find_ativa_por_substancia(ctx.paciente.id, entrada.substancia):
            raise ConflictoError(
                f"Já existe alergia ativa a '{entrada.substancia}' para este paciente. "
                "Registre uma nova reação nela em vez de duplicar."
            )

        nova = self._nova(ctx, entrada, autor)
        return self._executar(commit, lambda: self.repo.save(nova, commit=commit))

    @staticmethod
    def _nova(ctx, entrada, autor):
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
        """Atualiza codigo_substancia/flag_confirmado (substância não é editável,
        ver AlergiaAtualizarSchema). A mudança fica no log de auditoria da rota."""
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_do_paciente(uuid_alergia, ctx.paciente, incluindo_deletados=True)
        if alergia.deletado:
            raise ConflictoError(
                f"Alergia removida não pode ser atualizada: {uuid_alergia}. "
                "Restaure o registro antes de editar."
            )
        entrada = self._validar(AlergiaAtualizarSchema, dados)
        for campo, valor in entrada.campos_informados().items():
            setattr(alergia, campo, valor)
        return self._executar(commit, lambda: self.repo.save(alergia, commit=commit))

    def remover_alergia(self, uuid_atendimento: str, uuid_paciente: str, uuid_alergia: str,
                        dados: dict, autor: AutorClinico, commit: bool = True):
        """Soft delete com motivo, autor e atendimento. Remover de novo cai em
        404 (find_by_uuid filtra deletado)."""
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_do_paciente(uuid_alergia, ctx.paciente)
        entrada = self._validar(AlergiaRemoverSchema, dados)
        self._executar(commit, lambda: self.repo.soft_delete(
            alergia, entrada.motivo_delete, entrada.observacoes_delete,
            deletado_por=autor.id_usuario, id_atendimento_delecao=ctx.atendimento.id,
            commit=commit))
        return alergia

    def restaurar_alergia(self, uuid_atendimento: str, uuid_paciente: str, uuid_alergia: str,
                          autor: AutorClinico, commit: bool = True):
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        alergia = self._alergia_do_paciente(uuid_alergia, ctx.paciente, incluindo_deletados=True)
        if not alergia.deletado:
            raise ConflictoError(f"Alergia não está removida, nada a restaurar: {uuid_alergia}")
        if self.repo.find_ativa_por_substancia(ctx.paciente.id, alergia.substancia):
            raise ConflictoError(
                f"Já existe alergia ativa a '{alergia.substancia}'; não é possível restaurar a removida."
            )
        return self._executar(commit, lambda: self.repo.restaurar(alergia, commit=commit))

    # ------------------------------------------------------- estatísticas
    def top_substancias(self, id_empresa: int, limite: int = 10):
        return self.repo.top_substancias(id_empresa=id_empresa, limite=limite)

    def gravidade_por_substancia(self, id_empresa: int, substancia: str):
        return self.repo.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)

    def gravidade_geral(self, id_empresa: int):
        return self.repo.gravidade_geral(id_empresa=id_empresa)