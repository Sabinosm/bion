"""medicamento_em_uso_service.py

Regras de negócio dos medicamentos em uso do paciente: registrar, substituir,
encerrar, remover e restaurar, além da leitura, da verificação de interações e da
estatística de uso contínuo.

A leitura exige login e o tenant (empresa). Toda escrita passa pela checagem comum
de escrita clínica (atendimento em andamento do PRÓPRIO profissional, do mesmo
paciente, etc.). Não há atualização no lugar: mudar dose ou frequência é
substituir (fecha o antigo e cria o novo, numa transação só). Só registro ativo
muda: removido ou já encerrado vale 409. O mesmo medicamento do catálogo não pode
estar ativo duas vezes para o paciente, e datas de encerramento ou mudança não
podem ser anteriores ao início do uso. Quando a data de mudança ou de encerramento não
vem, o padrão é hoje no fuso da empresa. Remover é soft delete com motivo.

Todo método de escrita aceita `commit` (padrão True). Com commit=False o service só
dá flush: é o que o controller usa sob a ação sensível, onde o decorator comita a
alteração e o log numa transação única.

A verificação de interações é informativa e não bloqueia nada: cruza só os
medicamentos ATIVOS com vínculo no catálogo, e lista vazia não prova ausência de
interação (a base cobre só o que está cadastrado).
"""
from datetime import date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, MedicamentoEmUsoRepository
from src.domains.empresa.repository import EmpresaRepository
from src.domains.medicamentos.repository import CatalogoMedicamentosRepository
from src.domains.medicamentos.interacoes.interacoes_medicamento_repository import InteracoesMedicamentosRepository
from src.domains.paciente.schemas.schema_medicamento_em_uso import (
    MedicamentoEmUsoCreateSchema, MedicamentoEmUsoEncerrarSchema,
    MedicamentoEmUsoSubstituirSchema, MedicamentoEmUsoRemoverSchema,
)
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from .comum import validar_schema, paciente_ou_404, hoje_na_empresa


class MedicamentoEmUsoService:

    def __init__(self):
        self.repo = MedicamentoEmUsoRepository()
        self.paciente_repo = PacienteRepository()
        self.catalogo_repo = CatalogoMedicamentosRepository()
        self.empresa_repo = EmpresaRepository()
        self.interacoes_repo = InteracoesMedicamentosRepository()
        self.contexto = ContextoClinicoService()

    # ---------- helpers ----------
    def _do_paciente_ou_404(self, uuid_medicamento: str, paciente, incluir_deletados: bool = False):
        """Registro do paciente pelo UUID. Raises: RecursoNaoEncontradoError (inexistente ou de outro paciente)."""
        buscar = (self.repo.find_by_uuid_incluindo_deletados if incluir_deletados
                  else self.repo.find_by_uuid)
        m = buscar(uuid_medicamento)
        if not m or m.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Medicamento em uso não encontrado: {uuid_medicamento}")
        return m

    def _ativo_do_paciente(self, uuid_medicamento: str, paciente):
        """Registro ativo do paciente.

        Raises:
            ConflictoError: registro removido ou já encerrado.
        """
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
        """Raises: DadosInvalidosError se a data é anterior ao início do uso."""
        if medicamento.desde and data < medicamento.desde:
            raise DadosInvalidosError(
                f"Data {data.isoformat()} anterior ao início do uso ({medicamento.desde.isoformat()})."
            )

    @staticmethod
    def _novo(**campos):
        """Instancia o MedicamentoEmUso (import local: evita ciclo de models). Não persiste."""
        from src.models.pacientes import MedicamentoEmUso
        return MedicamentoEmUso(**campos)

    # ---------- leitura ----------
    def listar_medicamentos_em_uso(self, uuid_paciente: str, id_empresa: int,
                                   apenas_ativos: bool = False):
        """Medicamentos não removidos do paciente (ativos primeiro)."""
        p = paciente_ou_404(self.paciente_repo, uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id, apenas_ativos=apenas_ativos)

    def verificar_interacoes_do_paciente(self, uuid_paciente: str, id_empresa: int) -> dict:
        """Cruza os medicamentos ATIVOS do paciente com o catálogo de interações (formato em
        _montar_alertas)."""
        p = paciente_ou_404(self.paciente_repo, uuid_paciente, id_empresa)
        return self._montar_alertas(self.repo.find_por_paciente(p.id, apenas_ativos=True))

    def _montar_alertas(self, ativos) -> dict:
        """Informativo, não bloqueia nada. Lista vazia NÃO prova ausência de interação: a base cobre
        só o que está cadastrado, e itens sem vínculo com o catálogo (nao_verificados) nem entram
        na checagem."""
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
        """Registra um medicamento ATIVO. Retorna (medicamento, alertas) com os alertas de
        interação já considerando o novo item.

        Raises:
            DadosInvalidosError: corpo inválido, uuid_catalogo inexistente, ou sem descrição.
            ConflictoError: o medicamento do catálogo já está ativo para o paciente.
        """
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = validar_schema(MedicamentoEmUsoCreateSchema, dados)

        catalogo = None
        if entrada.uuid_catalogo:
            catalogo = self.catalogo_repo.find_by_uuid(entrada.uuid_catalogo)
            if not catalogo:
                raise DadosInvalidosError(
                    f"uuid_catalogo inválido: {entrada.uuid_catalogo} não existe no catálogo.",
                    campo="uuid_catalogo",
                )
            if self.repo.existe_ativo_do_catalogo(ctx.paciente.id, catalogo.id):
                raise ConflictoError(
                    "Este medicamento já está em uso ativo para o paciente. "
                    "Use substituir (mudança de dose/frequência) ou encerrar."
                )

        descricao = entrada.descricao or (catalogo.principio_ativo if catalogo else None)
        if not descricao:
            raise DadosInvalidosError(
                "Descrição obrigatória.",
                erros={"descricao": "obrigatória (o catálogo não tem princípio ativo)"},
            )

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
        """Mudança de dose, frequência ou descrição: cria o registro novo e fecha o antigo
        ('concluido', ate=data_mudanca, id_substituida_por), atomicamente. Retorna o registro novo.

        Raises:
            ConflictoError: registro removido ou já encerrado.
            DadosInvalidosError: data anterior ao início do uso, ou nenhuma alteração.
        """
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        antigo = self._ativo_do_paciente(uuid_medicamento, ctx.paciente)
        entrada = validar_schema(MedicamentoEmUsoSubstituirSchema, dados)

        mudanca = entrada.data_mudanca or hoje_na_empresa(self.empresa_repo, autor.id_empresa)
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
        """Fecha o tratamento como 'interrompido' ou 'concluido'.

        Raises:
            ConflictoError: registro removido ou já encerrado.
            DadosInvalidosError: data de encerramento anterior ao início do uso.
        """
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        m = self._ativo_do_paciente(uuid_medicamento, ctx.paciente)
        entrada = validar_schema(MedicamentoEmUsoEncerrarSchema, dados)

        ate = entrada.ate or hoje_na_empresa(self.empresa_repo, autor.id_empresa)
        self._exigir_data_apos_desde(ate, m)
        return self.repo.fechar(m, entrada.status_uso, ate, autor.id_usuario,
                                ctx.atendimento.id, commit=commit)

    def remover(self, uuid_atendimento: str, uuid_paciente: str,
                uuid_medicamento: str, dados: dict, autor: AutorClinico,
                commit: bool = True):
        """Soft delete com motivo, autor e atendimento. Retorna o registro removido (o controller
        precisa dele para a auditoria). A busca já filtra deletado, então remover de novo cai em
        404 (não vaza se já foi removido ou nunca existiu)."""
        ctx = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        m = self._do_paciente_ou_404(uuid_medicamento, ctx.paciente)
        entrada = validar_schema(MedicamentoEmUsoRemoverSchema, dados)
        self.repo.soft_delete(m, entrada.motivo_delete, entrada.observacoes_delete,
                              autor.id_usuario, ctx.atendimento.id, commit=commit)
        return m

    def restaurar(self, uuid_atendimento: str, uuid_paciente: str,
                  uuid_medicamento: str, autor: AutorClinico, commit: bool = True):
        """Reverte um soft delete.

        Raises:
            ConflictoError: não está removido, ou restaurar criaria um segundo registro ativo do
                mesmo medicamento.
        """
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

    # ---------- estatísticas ----------
    def percentual_pacientes_em_uso_continuo(self, id_empresa: int):
        """% de pacientes da empresa com ao menos um medicamento ativo (ver o repository)."""
        return self.repo.percentual_pacientes_em_uso_continuo(id_empresa=id_empresa)
