"""doenca_cronica_service.py

Regras de negócio das doenças crônicas do paciente: adicionar, atualizar
(observações), revisar, remover e restaurar, além da leitura e da estatística.

A leitura e a estatística exigem só o tenant (empresa). Toda escrita acontece
DENTRO de um Atendimento em andamento do próprio profissional (checagem comum de
escrita clínica), e o registro guarda quem escreveu e em qual Atendimento (criação,
encerramento e remoção).

Histórico: status, CID e data de início NÃO são editados no lugar. A revisão fecha
a linha vigente e cria uma nova (fechar + criar novo), e a atualização mexe só nas
observações. Só a linha vigente muda ou é removida: linha removida ou encerrada
por revisão vale 409. Não pode haver duas doenças vigentes com o mesmo CID. Remover
é soft delete com motivo.

`commit=False` só faz flush, usado pela rota de ação sensível e pela rota agregada
do binário, que compõem várias escritas atômicas.
"""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, DoencaCronicaRepository
from src.domains.paciente.schemas.schema_doenca_cronica import (
    DoencaCronicaCreateSchema, DoencaCronicaAtualizarSchema, DoencaCronicaRevisarSchema,
    DoencaCronicaRemoverSchema,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from .comum import validar_schema, paciente_ou_404, executar_com_rollback

_CAMPOS_REVISAVEIS = ("codigo_cid10", "descricao_cid10", "desde", "status", "observacoes")


class DoencaCronicaService:

    def __init__(self):
        self.repo = DoencaCronicaRepository()
        self._paciente_repo = PacienteRepository()
        self._ctx = ContextoClinicoService()

    # ------------------------------------------------------------ helpers
    def _doenca_do_paciente(self, uuid_doenca: str, paciente, incluindo_deletados: bool = False):
        """Doença do paciente pelo UUID. Raises: RecursoNaoEncontradoError (inexistente ou de outro paciente)."""
        busca = (self.repo.find_by_uuid_incluindo_deletados if incluindo_deletados
                 else self.repo.find_by_uuid)
        d = busca(uuid_doenca)
        if not d or d.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Doença crônica não encontrada: {uuid_doenca}")
        return d

    @staticmethod
    def _exigir_vigente(doenca, acao: str) -> None:
        """Só a linha vigente muda/é removida.

        Raises:
            ConflictoError: linha removida ou encerrada por revisão.
        """
        if doenca.deletado:
            raise ConflictoError(
                f"Doença crônica removida não pode ser {acao}: {doenca.uuid}. "
                "Restaure o registro antes."
            )
        if doenca.encerrado_em is not None:
            raise ConflictoError(
                f"Doença crônica já encerrada por revisão (histórico) não pode ser {acao}: "
                f"{doenca.uuid}. Atue no registro vigente."
            )

    def _exigir_sem_duplicata(self, id_paciente: int, codigo_cid10: str, ignorar_id=None) -> None:
        """Raises: ConflictoError se já há doença vigente com o mesmo CID."""
        if self.repo.find_aberta_por_cid(id_paciente, codigo_cid10, ignorar_id=ignorar_id):
            raise ConflictoError(
                f"Já existe doença crônica vigente com CID '{codigo_cid10}' para este paciente. "
                "Use a revisão do registro existente em vez de duplicar."
            )

    # ------------------------------------------------------------ leitura
    def listar_doencas(self, uuid_paciente: str, id_empresa: int):
        """Doenças vigentes (pré-preenchimento dos atendimentos seguintes)."""
        p = paciente_ou_404(self._paciente_repo, uuid_paciente, id_empresa)
        return self.listar_doencas_do_paciente(p)

    def listar_doencas_do_paciente(self, paciente):
        """Doenças vigentes de um paciente JÁ carregado (evita refazer a busca por UUID quando
        quem chama, como o prontuário, já tem o paciente)."""
        return self.repo.find_por_paciente(paciente.id)

    def listar_historico(self, uuid_paciente: str, id_empresa: int):
        """Vigentes + encerradas por revisão (linha do tempo), sem removidas."""
        p = paciente_ou_404(self._paciente_repo, uuid_paciente, id_empresa)
        return self.repo.find_historico_por_paciente(p.id)

    # ------------------------------------------------------------ escrita
    def adicionar_doenca(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                         autor: AutorClinico, commit: bool = True):
        """Registra uma doença crônica no atendimento em andamento.

        Raises:
            DadosInvalidosError: corpo inválido (erros por campo).
            ConflictoError: já existe doença vigente com o mesmo CID.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = validar_schema(DoencaCronicaCreateSchema, dados)
        self._exigir_sem_duplicata(ctx.paciente.id, entrada.codigo_cid10)

        nova = self._nova(ctx, autor, entrada.codigo_cid10, entrada.descricao_cid10,
                          entrada.desde, entrada.status, entrada.observacoes)
        return executar_com_rollback(self.repo, commit, lambda: self.repo.save(nova, commit=commit))

    @staticmethod
    def _nova(ctx, autor, codigo_cid10, descricao_cid10, desde, status, observacoes):
        """Monta a DoencaCronica com autor e atendimento de origem. Só instancia; não persiste."""
        from src.models.pacientes import DoencaCronica
        return DoencaCronica(
            id_paciente=ctx.paciente.id,
            codigo_cid10=codigo_cid10,
            descricao_cid10=descricao_cid10,
            desde=desde,
            status=status,
            observacoes=observacoes,
            criado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )

    def atualizar_doenca(self, uuid_atendimento: str, uuid_paciente: str, uuid_doenca: str,
                         dados: dict, autor: AutorClinico, commit: bool = True):
        """Atualiza só `observacoes` (ver DoencaCronicaAtualizarSchema). Status, CID e início mudam
        por revisar_doenca. A mudança fica no log de auditoria.

        Raises:
            RecursoNaoEncontradoError: doença inexistente ou de outro paciente.
            ConflictoError: doença removida ou já encerrada por revisão.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        doenca = self._doenca_do_paciente(uuid_doenca, ctx.paciente, incluindo_deletados=True)
        self._exigir_vigente(doenca, "atualizada")
        entrada = validar_schema(DoencaCronicaAtualizarSchema, dados)
        for campo, valor in entrada.campos_informados().items():
            setattr(doenca, campo, valor)
        return executar_com_rollback(self.repo, commit, lambda: self.repo.save(doenca, commit=commit))

    def revisar_doenca(self, uuid_atendimento: str, uuid_paciente: str, uuid_doenca: str,
                       dados: dict, autor: AutorClinico, commit: bool = True):
        """Fechar + criar novo: a linha vigente é encerrada (quem, quando e em qual atendimento) e
        aponta para a nova, que nasce com os valores revisados e o atendimento atual como origem.
        Devolve a NOVA linha. O que não vier no corpo é copiado da vigente.

        Raises:
            DadosInvalidosError: sem mudança real em relação à vigente (422).
            ConflictoError: doença removida/encerrada, ou o novo CID já existe vigente.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        antiga = self._doenca_do_paciente(uuid_doenca, ctx.paciente, incluindo_deletados=True)
        self._exigir_vigente(antiga, "revisada")
        entrada = validar_schema(DoencaCronicaRevisarSchema, dados)

        valores = {c: getattr(antiga, c) for c in _CAMPOS_REVISAVEIS}
        valores.update(entrada.campos_informados())
        if all(valores[c] == getattr(antiga, c) for c in _CAMPOS_REVISAVEIS):
            raise DadosInvalidosError("Nenhuma alteração em relação ao registro vigente.")

        if valores["codigo_cid10"] != antiga.codigo_cid10:
            self._exigir_sem_duplicata(ctx.paciente.id, valores["codigo_cid10"], ignorar_id=antiga.id)

        nova = self._nova(ctx, autor, valores["codigo_cid10"], valores["descricao_cid10"],
                          valores["desde"], valores["status"], valores["observacoes"])
        return executar_com_rollback(self.repo, commit, lambda: self.repo.substituir(
            antiga, nova, encerrado_por=autor.id_usuario,
            id_atendimento_encerramento=ctx.atendimento.id, commit=commit))

    def remover_doenca(self, uuid_atendimento: str, uuid_paciente: str, uuid_doenca: str,
                       dados: dict, autor: AutorClinico, commit: bool = True):
        """Soft delete com motivo, autor e atendimento. Remover de novo cai em 404 (a busca filtra
        deletado). Só a linha vigente é removida: linha encerrada é histórico e corrige-se
        revisando a vigente.

        Raises:
            RecursoNaoEncontradoError: doença inexistente, de outro paciente ou já removida.
            ConflictoError: linha encerrada por revisão.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        doenca = self._doenca_do_paciente(uuid_doenca, ctx.paciente)
        self._exigir_vigente(doenca, "removida")
        entrada = validar_schema(DoencaCronicaRemoverSchema, dados)
        executar_com_rollback(self.repo, commit, lambda: self.repo.soft_delete(
            doenca, entrada.motivo_delete, entrada.observacoes_delete,
            deletado_por=autor.id_usuario, id_atendimento_delecao=ctx.atendimento.id,
            commit=commit))
        return doenca

    def restaurar_doenca(self, uuid_atendimento: str, uuid_paciente: str, uuid_doenca: str,
                         autor: AutorClinico, commit: bool = True):
        """Reverte o soft delete.

        Raises:
            ConflictoError: a doença não está removida, ou já existe outra vigente com o mesmo CID.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        doenca = self._doenca_do_paciente(uuid_doenca, ctx.paciente, incluindo_deletados=True)
        if not doenca.deletado:
            raise ConflictoError(f"Doença crônica não está removida, nada a restaurar: {uuid_doenca}")
        self._exigir_sem_duplicata(ctx.paciente.id, doenca.codigo_cid10, ignorar_id=doenca.id)
        return executar_com_rollback(self.repo, commit, lambda: self.repo.restaurar(doenca, commit=commit))

    # ------------------------------------------------------- estatísticas
    def top_cid_ativas(self, id_empresa: int, limite: int = 10):
        """Doenças crônicas ativas mais comuns na base da empresa (ver o repository)."""
        return self.repo.top_cid_ativas(id_empresa=id_empresa, limite=limite)
