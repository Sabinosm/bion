from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, DoencaCronicaRepository
from src.domains.paciente.schemas.schema_doenca_cronica import (
    DoencaCronicaCreateSchema, DoencaCronicaAtualizarSchema, DoencaCronicaRevisarSchema,
    DoencaCronicaRemoverSchema, erros_pydantic_por_campo,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico

_CAMPOS_REVISAVEIS = ("codigo_cid10", "descricao_cid10", "desde", "status", "observacoes")


class DoencaCronicaService:
    """Doenças crônicas do paciente.

    LEITURA (listar_*, estatísticas): só tenant (id_empresa).

    ESCRITA (adicionar/atualizar/revisar/remover/restaurar): sempre DENTRO
    de um Atendimento `em-andamento` do próprio profissional -- a checagem
    inteira vive em ContextoClinicoService.exigir_escrita. O registro guarda
    quem escreveu e em qual Atendimento (criado_por / id_atendimento_origem;
    encerrado_por / id_atendimento_encerramento; deletado_por /
    id_atendimento_delecao).

    Histórico: status, CID e desde NÃO são editados no lugar. `revisar`
    fecha a linha vigente e cria uma nova (fechar + criar novo);
    `atualizar` mexe só em `observacoes`.

    `commit=False` só faz flush: usado pela rota acao_sensivel e pela rota
    agregada do binário, que compõem várias escritas atômicas.
    """

    def __init__(self):
        self.repo = DoencaCronicaRepository()
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

    def _doenca_do_paciente(self, uuid_doenca: str, paciente, incluindo_deletados: bool = False):
        busca = (self.repo.find_by_uuid_incluindo_deletados if incluindo_deletados
                 else self.repo.find_by_uuid)
        d = busca(uuid_doenca)
        if not d or d.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Doença crônica não encontrada: {uuid_doenca}")
        return d

    @staticmethod
    def _exigir_vigente(doenca, acao: str) -> None:
        """Só a linha vigente muda/é removida; removida ou encerrada -> 409."""
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
        if self.repo.find_aberta_por_cid(id_paciente, codigo_cid10, ignorar_id=ignorar_id):
            raise ConflictoError(
                f"Já existe doença crônica vigente com CID '{codigo_cid10}' para este paciente. "
                "Use a revisão do registro existente em vez de duplicar."
            )

    def _executar(self, commit: bool, fn):
        """Se este service é dono do commit, desfaz tudo em caso de falha."""
        try:
            return fn()
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    # ------------------------------------------------------------ leitura
    def listar_doencas(self, uuid_paciente: str, id_empresa: int):
        """Doenças vigentes (pré-preenchimento dos atendimentos seguintes)."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    def listar_historico(self, uuid_paciente: str, id_empresa: int):
        """Vigentes + encerradas por revisão (linha do tempo), sem removidas."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_historico_por_paciente(p.id)

    # ------------------------------------------------------------ escrita
    def adicionar_doenca(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                         autor: AutorClinico, commit: bool = True):
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = self._validar(DoencaCronicaCreateSchema, dados)
        self._exigir_sem_duplicata(ctx.paciente.id, entrada.codigo_cid10)

        nova = self._nova(ctx, autor, entrada.codigo_cid10, entrada.descricao_cid10,
                          entrada.desde, entrada.status, entrada.observacoes)
        return self._executar(commit, lambda: self.repo.save(nova, commit=commit))

    @staticmethod
    def _nova(ctx, autor, codigo_cid10, descricao_cid10, desde, status, observacoes):
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
        """Atualiza só `observacoes` (ver DoencaCronicaAtualizarSchema). Status,
        CID e desde mudam por revisar_doenca. A mudança fica no log de auditoria."""
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        doenca = self._doenca_do_paciente(uuid_doenca, ctx.paciente, incluindo_deletados=True)
        self._exigir_vigente(doenca, "atualizada")
        entrada = self._validar(DoencaCronicaAtualizarSchema, dados)
        for campo, valor in entrada.campos_informados().items():
            setattr(doenca, campo, valor)
        return self._executar(commit, lambda: self.repo.save(doenca, commit=commit))

    def revisar_doenca(self, uuid_atendimento: str, uuid_paciente: str, uuid_doenca: str,
                       dados: dict, autor: AutorClinico, commit: bool = True):
        """Fechar + criar novo: a linha vigente é encerrada (quem/quando/em
        qual atendimento) e aponta para a nova, que nasce com os valores
        revisados e o atendimento atual como origem. Devolve a NOVA linha.
        O que não vier no corpo é copiado da vigente; sem mudança real -> 422."""
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        antiga = self._doenca_do_paciente(uuid_doenca, ctx.paciente, incluindo_deletados=True)
        self._exigir_vigente(antiga, "revisada")
        entrada = self._validar(DoencaCronicaRevisarSchema, dados)

        valores = {c: getattr(antiga, c) for c in _CAMPOS_REVISAVEIS}
        valores.update(entrada.campos_informados())
        if all(valores[c] == getattr(antiga, c) for c in _CAMPOS_REVISAVEIS):
            raise DadosInvalidosError("Nenhuma alteração em relação ao registro vigente.")

        if valores["codigo_cid10"] != antiga.codigo_cid10:
            self._exigir_sem_duplicata(ctx.paciente.id, valores["codigo_cid10"], ignorar_id=antiga.id)

        nova = self._nova(ctx, autor, valores["codigo_cid10"], valores["descricao_cid10"],
                          valores["desde"], valores["status"], valores["observacoes"])
        return self._executar(commit, lambda: self.repo.substituir(
            antiga, nova, encerrado_por=autor.id_usuario,
            id_atendimento_encerramento=ctx.atendimento.id, commit=commit))

    def remover_doenca(self, uuid_atendimento: str, uuid_paciente: str, uuid_doenca: str,
                       dados: dict, autor: AutorClinico, commit: bool = True):
        """Soft delete com motivo, autor e atendimento. Remover de novo cai em
        404 (find_by_uuid filtra deletado). Só a linha vigente é removida:
        linha encerrada é histórico e corrige-se revisando a vigente."""
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        doenca = self._doenca_do_paciente(uuid_doenca, ctx.paciente)
        self._exigir_vigente(doenca, "removida")
        entrada = self._validar(DoencaCronicaRemoverSchema, dados)
        self._executar(commit, lambda: self.repo.soft_delete(
            doenca, entrada.motivo_delete, entrada.observacoes_delete,
            deletado_por=autor.id_usuario, id_atendimento_delecao=ctx.atendimento.id,
            commit=commit))
        return doenca

    def restaurar_doenca(self, uuid_atendimento: str, uuid_paciente: str, uuid_doenca: str,
                         autor: AutorClinico, commit: bool = True):
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        doenca = self._doenca_do_paciente(uuid_doenca, ctx.paciente, incluindo_deletados=True)
        if not doenca.deletado:
            raise ConflictoError(f"Doença crônica não está removida, nada a restaurar: {uuid_doenca}")
        self._exigir_sem_duplicata(ctx.paciente.id, doenca.codigo_cid10, ignorar_id=doenca.id)
        return self._executar(commit, lambda: self.repo.restaurar(doenca, commit=commit))

    # ------------------------------------------------------- estatísticas
    # --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10):
        return self.repo.top_cid_ativas(id_empresa=id_empresa, limite=limite)