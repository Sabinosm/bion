from datetime import date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.erros_pydantic import erros_pydantic_por_campo
from ..repositories import PacienteRepository, MedicamentoEmUsoRepository
from src.domains.medicamentos.repository import CatalogoMedicamentosRepository
from src.domains.medicamentos.interacoes.interacoes_medicamento_repository import InteracoesMedicamentosRepository
from src.domains.paciente.schemas.schema_medicamento_em_uso import (
    MedicamentoEmUsoCreateSchema, MedicamentoEmUsoEncerrarSchema,
    MedicamentoEmUsoSubstituirSchema, MedicamentoEmUsoRemoverSchema,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico


def _validar(schema_cls, dados: dict):
    try:
        return schema_cls(**dados)
    except ValidationError as e:
        raise DadosInvalidosError(erros_pydantic_por_campo(e))


class MedicamentoEmUsoService:
    """Medicamentos em uso do paciente.

    LEITURA: só login + tenant (empresa do usuário).
    ESCRITA: toda operação passa por ContextoClinicoService.exigir_escrita
    (atendimento em-andamento do PRÓPRIO profissional, do mesmo paciente,
    etc). Não há atualização no lugar: mudar dose/frequência = substituir
    (fecha o antigo + cria o novo, numa transação só).

    Todo método de escrita aceita `commit` (padrão True). Com commit=False
    o service só dá flush: é o que o controller usa sob @acao_sensivel, onde
    o decorator commita alteração + log numa transação única.
    """

    def __init__(self):
        self.repo = MedicamentoEmUsoRepository()
        self.paciente_repo = PacienteRepository()
        self.catalogo_repo = CatalogoMedicamentosRepository()
        self.interacoes_repo = InteracoesMedicamentosRepository()
        self.contexto = ContextoClinicoService()

    # ---------- helpers ----------

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def _do_paciente_ou_404(self, uuid_medicamento: str, paciente, incluir_deletados: bool = False):
        buscar = (self.repo.find_by_uuid_incluindo_deletados if incluir_deletados
                  else self.repo.find_by_uuid)
        m = buscar(uuid_medicamento)
        if not m or m.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Medicamento em uso não encontrado: {uuid_medicamento}")
        return m

    def _ativo_do_paciente(self, uuid_medicamento: str, paciente):
        """Registro ativo do paciente; removido ou já encerrado = 409."""
        m = self._do_paciente_ou_404(uuid_medicamento, paciente, incluir_deletados=True)
        if m.deletado:
            raise ConflictoError(
                f"Medicamento em uso removido não pode ser alterado: {uuid_medicamento}. "
                "Restaure o registro antes."
            )
        if m.status_uso != "ativo":
            raise ConflictoError(
                f"Medicamento em uso já encerrado ({m.status_uso}): {uuid_medicamento}."
            )
        return m

    @staticmethod
    def _exigir_data_apos_desde(data: date, medicamento) -> None:
        if medicamento.desde and data < medicamento.desde:
            raise DadosInvalidosError(
                f"Data {data.isoformat()} anterior ao início do uso ({medicamento.desde.isoformat()})."
            )

    @staticmethod
    def _novo(**campos):
        # import local: mesmo padrão do service anterior (evita ciclo de models)
        from src.models.pacientes import MedicamentoEmUso
        return MedicamentoEmUso(**campos)

    # ---------- leitura ----------

    def listar_medicamentos_em_uso(self, uuid_paciente: str, id_empresa: int,
                                   apenas_ativos: bool = False):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id, apenas_ativos=apenas_ativos)

    def verificar_interacoes_do_paciente(self, uuid_paciente: str, id_empresa: int) -> dict:
        """Cruza os medicamentos ATIVOS do paciente com o catálogo de
        interações. Ver _montar_alertas para o formato."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self._montar_alertas(self.repo.find_por_paciente(p.id, apenas_ativos=True))

    def _montar_alertas(self, ativos) -> dict:
        """Informativo, não bloqueia nada. Lista vazia NÃO prova ausência
        de interação: a base cobre só o que está cadastrado, e itens sem
        vínculo com o catálogo (nao_verificados) nem entram na checagem."""
        ids = [m.id_catalogo for m in ativos if m.id_catalogo is not None]
        pares = self.interacoes_repo.find_entre_medicamentos(ids)
        total = self.interacoes_repo.contar()
        nao_verificados = [
            {"uuid": m.uuid, "descricao": m.descricao}
            for m in ativos if m.id_catalogo is None
        ]

        if total == 0:
            aviso = "Base de interações ainda vazia: nenhuma checagem foi possível."
        else:
            aviso = ("Lista vazia não significa ausência de interação clínica: "
                     "a base cobre apenas as interações cadastradas.")
        if nao_verificados:
            aviso += " Há medicamentos sem vínculo com o catálogo, que não foram checados."

        return {
            "interacoes": [{
                "uuid": i.uuid,
                "medicamento_a": i.medicamento_a.principio_ativo,
                "medicamento_b": i.medicamento_b.principio_ativo,
                "gravidade": i.gravidade,
                "mecanismo_efeito": i.mecanismo_efeito,
                "recomendacao": i.recomendacao,
                "acao": i.acao,
            } for i in pares],
            "nao_verificados": nao_verificados,
            "cobertura": {"total_interacoes_na_base": total, "aviso": aviso},
        }

    # ---------- escrita (sempre dentro de um Atendimento) ----------

    def registrar(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                  autor: AutorClinico, commit: bool = True):
        """Registra um medicamento ATIVO. Retorna (medicamento, alertas)
        com os alertas de interação já considerando o novo item."""
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = _validar(MedicamentoEmUsoCreateSchema, dados)

        catalogo = None
        if entrada.uuid_catalogo:
            catalogo = self.catalogo_repo.find_by_uuid(entrada.uuid_catalogo)
            if not catalogo:
                raise DadosInvalidosError(
                    f"uuid_catalogo inválido: {entrada.uuid_catalogo} não existe no catálogo."
                )
            if self.repo.existe_ativo_do_catalogo(ctx.paciente.id, catalogo.id):
                raise ConflictoError(
                    "Este medicamento já está em uso ativo para o paciente. "
                    "Use substituir (mudança de dose/frequência) ou encerrar."
                )

        descricao = entrada.descricao or (catalogo.principio_ativo if catalogo else None)
        if not descricao:
            raise DadosInvalidosError({"descricao": "obrigatória (o catálogo não tem princípio ativo)"})

        m = self._novo(
            id_paciente=ctx.paciente.id,
            id_catalogo=catalogo.id if catalogo else None,
            descricao=descricao,
            dose=entrada.dose,
            frequencia=entrada.frequencia,
            desde=entrada.desde,
            status_uso="ativo",
            criado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )
        self.repo.add(m, commit=commit)
        ativos = self.repo.find_por_paciente(ctx.paciente.id, apenas_ativos=True)
        return m, self._montar_alertas(ativos)

    def substituir(self, uuid_atendimento: str, uuid_paciente: str,
                   uuid_medicamento: str, dados: dict, autor: AutorClinico,
                   commit: bool = True):
        """Mudança de dose/frequência/descrição: cria o registro novo e
        fecha o antigo ('concluido', ate=data_mudanca, id_substituida_por),
        atomicamente. Retorna o registro novo."""
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        antigo = self._ativo_do_paciente(uuid_medicamento, ctx.paciente)
        entrada = _validar(MedicamentoEmUsoSubstituirSchema, dados)

        mudanca = entrada.data_mudanca or date.today()
        self._exigir_data_apos_desde(mudanca, antigo)

        novos = entrada.campos_informados()
        if not any(getattr(antigo, campo) != valor for campo, valor in novos.items()):
            raise DadosInvalidosError("Nenhuma alteração em relação ao registro atual.")

        novo = self._novo(
            id_paciente=antigo.id_paciente,
            id_catalogo=antigo.id_catalogo,
            descricao=novos.get("descricao", antigo.descricao),
            dose=novos.get("dose", antigo.dose),
            frequencia=novos.get("frequencia", antigo.frequencia),
            desde=mudanca,
            status_uso="ativo",
            criado_por=autor.id_usuario,
            id_atendimento_origem=ctx.atendimento.id,
        )
        self.repo.add(novo, commit=False)   # flush: garante novo.id
        self.repo.fechar(antigo, "concluido", mudanca, autor.id_usuario,
                         ctx.atendimento.id, id_substituida_por=novo.id, commit=commit)
        return novo

    def encerrar(self, uuid_atendimento: str, uuid_paciente: str,
                 uuid_medicamento: str, dados: dict, autor: AutorClinico,
                 commit: bool = True):
        """Fecha o tratamento como 'interrompido' ou 'concluido'."""
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        m = self._ativo_do_paciente(uuid_medicamento, ctx.paciente)
        entrada = _validar(MedicamentoEmUsoEncerrarSchema, dados)

        ate = entrada.ate or date.today()
        self._exigir_data_apos_desde(ate, m)
        return self.repo.fechar(m, entrada.status_uso, ate, autor.id_usuario,
                                ctx.atendimento.id, commit=commit)

    def remover(self, uuid_atendimento: str, uuid_paciente: str,
                uuid_medicamento: str, dados: dict, autor: AutorClinico,
                commit: bool = True):
        """Soft delete com motivo, autor e atendimento. Retorna o registro
        removido (o controller precisa dele para a auditoria). find_by_uuid já
        filtra deletado, então remover de novo cai em 404 (não vaza se
        já foi removido ou nunca existiu)."""
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        m = self._do_paciente_ou_404(uuid_medicamento, ctx.paciente)
        entrada = _validar(MedicamentoEmUsoRemoverSchema, dados)
        self.repo.soft_delete(m, entrada.motivo_delete, entrada.observacoes_delete,
                              autor.id_usuario, ctx.atendimento.id, commit=commit)
        return m

    def restaurar(self, uuid_atendimento: str, uuid_paciente: str,
                  uuid_medicamento: str, autor: AutorClinico, commit: bool = True):
        """Reverte um soft delete (409 se não estiver removido, ou se
        restaurar criaria um segundo registro ativo do mesmo medicamento)."""
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        m = self._do_paciente_ou_404(uuid_medicamento, ctx.paciente, incluir_deletados=True)
        if not m.deletado:
            raise ConflictoError(
                f"Medicamento em uso não está removido, nada a restaurar: {uuid_medicamento}"
            )
        if (m.status_uso == "ativo" and m.id_catalogo is not None
                and self.repo.existe_ativo_do_catalogo(ctx.paciente.id, m.id_catalogo, excluir_id=m.id)):
            raise ConflictoError(
                "Já existe um registro ativo deste medicamento; não é possível restaurar este."
            )
        return self.repo.restaurar(m, commit=commit)

    # --- F2: Pacientes em uso contínuo de medicação (%) ---
    def percentual_pacientes_em_uso_continuo(self, id_empresa: int):
        return self.repo.percentual_pacientes_em_uso_continuo(id_empresa=id_empresa)
