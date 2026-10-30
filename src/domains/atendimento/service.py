"""service.py

Regras de negócio do ciclo de vida do Atendimento: abertura de triagem,
avaliação médica e reavaliação, finalização, cancelamento e as consultas de
leitura usadas pelas telas e pela estatística.

O Atendimento é uma etapa dentro de uma Consulta (o episódio de um problema de
saúde) e não tem empresa própria: a posse vem da Consulta, então toda busca
filtra pela empresa da sessão e "não existe" e "é de outra empresa" dão o mesmo
404. Abrir exige consentimento LGPD válido e Consulta não encerrada, e só pode
haver um Atendimento em andamento por vez; a abertura trava a linha da Consulta
para que duas aberturas simultâneas não criem dois em andamento. Criar,
finalizar ou cancelar o Atendimento e recalcular o status da Consulta formam uma
única transação.

Um Atendimento tem o mesmo profissional do início ao fim: só quem o abriu o
finaliza ou cancela (403). Finalizar exige o binário completo e nenhuma
pendência clínica (avaliação da IA em andamento ou prescrição em rascunho) e,
na mesma transação, reconcilia o binário com os registros ativos do paciente;
cancelar não exige nem reconcilia nada, porque abandonar o atendimento não pode
depender de preencher dados. Avaliação médica e reavaliação só são finalizadas
por médico, e a reavaliação só abre com a Consulta no status que indica
atendimento concluído com a Consulta ainda aberta.

Na abertura o binário é derivado do paciente: a seção consistente com a última
conferência é repassada como automática, e a seção cujo dado mudou desde então
fica a revisar e trava a finalização até ser confirmada.
"""

from datetime import datetime, timezone

from src.core.exceptions import (
    RecursoNaoEncontradoError, ConflictoError, PermissaoNegadaError, DadosInvalidosError,
)
from .repository import AtendimentoRepository
from src.domains.consulta.paciente_resumo_service import bloco_paciente
from src.domains.consulta.continuar_service import STATUS_PARA_REAVALIACAO, continuidade_atendimento
from src.models.clinico import Atendimento
from .binario.binario_gate import exigir_binario_completo
from src.domains.consulta.repository import ConsultaRepository
from src.domains.consulta.service import ConsultaService
from src.domains.consulta.status_sync import sincronizar_status_consulta

TIPOS_SOMENTE_MEDICO = ("avaliacao-medica", "reavaliacao")

MOTIVOS_CANCELAMENTO = (
    "erro-abertura", "paciente-nao-compareceu", "paciente-recusou", "transferencia", "outro",
)


class AtendimentoService:
    """Casos de uso relacionados à abertura, consulta, finalização e cancelamento de Atendimentos.

    MODELO: a Consulta é o EPISÓDIO de um problema de saúde; os Atendimentos
    são etapas dentro dela (1:N). Retornos pelo mesmo problema entram na
    mesma Consulta. Não há ordem obrigatória nem correlação entre triagem e
    avaliação médica: pode haver triagem sem avaliação, avaliação sem
    triagem (clínica sem enfermeiro), e qualquer tipo pode se repetir.

    Única restrição de fluxo: UM Atendimento em andamento por vez na
    Consulta (o status_consulta é derivado do último Atendimento).
    """

    def __init__(self):
        self.repo = AtendimentoRepository()
        self.consulta_repo = ConsultaRepository()
        self.consulta_svc = ConsultaService()

    # ------------------------------------------------------------- leitura
    def buscar_por_uuid(self, uuid: str, id_empresa: int):
        """Retorna um Atendimento da empresa ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid, id_empresa)
        if not e:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid}")
        return e

    def _com_paciente(self, a, id_usuario: int = None) -> dict:
        """Atendimento.to_dict() + bloco `paciente` (via consulta.paciente; nome descriptografado).

        Com `id_usuario`, soma pode_continuar, proxima_acao e motivo_bloqueio (ver continuar_service.py).
        Nome é PII: só use em rota de médico/enfermeiro."""
        d = a.to_dict()
        d["paciente"] = bloco_paciente(a.consulta.paciente if a.consulta else None)
        if id_usuario is not None:
            d.update(continuidade_atendimento(a, id_usuario))
        return d

    def buscar_resumo(self, uuid: str, id_empresa: int, id_usuario: int = None) -> dict:
        """Detalhe do Atendimento já com o paciente (404 igual para 'não existe' e 'outra empresa').
        Com `id_usuario`, inclui os campos de continuidade."""
        return self._com_paciente(self.buscar_por_uuid(uuid, id_empresa), id_usuario)

    def listar(self, id_empresa: int):
        """Lista os Atendimentos da empresa."""
        return self.repo.find_all(id_empresa)

    def listar_por_consulta(self, uuid_consulta: str, id_empresa: int):
        """Lista os Atendimentos de uma Consulta da empresa. A posse é checada na
        Consulta; `find_por_consulta` em si não filtra empresa."""
        c = self.consulta_svc.buscar_por_uuid(uuid_consulta, id_empresa)
        return self.repo.find_por_consulta(c.id)

    @staticmethod
    def _profissional(a) -> dict | None:
        """Quem fez o atendimento (nome e função clínica atual), para a linha do tempo. Não é PII
        de paciente: são colegas da mesma empresa. A função é a ATUAL do profissional."""
        u = a.usuario
        if not u:
            return None
        return {"uuid": u.uuid, "nome_completo": u.nome_completo, "funcao_clinica": u.funcao_clinica}

    def listar_resumo_por_consulta(self, uuid_consulta: str, id_empresa: int):
        """Linha do tempo da Consulta: (itens, uuid_paciente). Cada item é Atendimento.to_dict() +
        `profissional`. 404 igual para 'não existe' e 'outra empresa'. Custo: ~2 queries por
        atendimento (usuário e papéis), poucos por consulta."""
        c = self.consulta_svc.buscar_por_uuid(uuid_consulta, id_empresa)
        itens = [{**a.to_dict(), "profissional": self._profissional(a)}
                 for a in self.repo.find_por_consulta(c.id)]
        return itens, (c.paciente.uuid if c.paciente else None)

    # -------------------------------------------------------- transação
    def _sincronizar(self, consulta, commit: bool):
        """Recalcula status_consulta a partir dos Atendimentos atuais.
        Com commit=False fica pendente, junto com a escrita do Atendimento."""
        atendimentos = self.repo.find_por_consulta(consulta.id)
        sincronizar_status_consulta(consulta, atendimentos)
        self.consulta_repo.save(consulta, commit=commit)

    def _validar_abertura(self, consulta, status_permitidos=None):
        """Valida, com a Consulta já travada, se um novo Atendimento pode abrir: Consulta não
        encerrada, consentimento válido, nenhum outro em andamento e, quando
        `status_permitidos` é informado, status_consulta dentro dele (usado pela reavaliação)."""
        if consulta.status_consulta == "encerrada":
            raise ConflictoError("Consulta encerrada: não é possível abrir novo atendimento.")
        self.consulta_svc.exigir_consentimento(consulta)
        self._exigir_sem_em_andamento(consulta)
        if status_permitidos is not None and consulta.status_consulta not in status_permitidos:
            raise ConflictoError(
                "Reavaliação só pode ser aberta depois de um atendimento concluído "
                f"(status atual da Consulta: {consulta.status_consulta})."
            )

    def _abrir(self, uuid_consulta: str, tipo_atendimento: str, id_usuario: int,
               id_empresa: int, status_permitidos=None):
        """Caminho único de abertura: busca a Consulta da empresa, trava a linha, valida e cria o
        Atendimento. Qualquer falha antes da criação faz rollback para soltar a trava."""
        c = self.consulta_svc.buscar_por_uuid(uuid_consulta, id_empresa)
        try:
            self.consulta_repo.travar(c)
            self._validar_abertura(c, status_permitidos)
        except Exception:
            self.repo.rollback()
            raise
        return self._criar(c, tipo_atendimento, id_usuario)

    def _exigir_sem_em_andamento(self, consulta):
        """Um Atendimento em andamento por vez na Consulta."""
        if any(a.status == "em-andamento" for a in self.repo.find_por_consulta(consulta.id)):
            raise ConflictoError(
                "Já existe um atendimento em andamento nesta Consulta: finalize-o antes de abrir outro."
            )

    def _criar(self, consulta, tipo_atendimento: str, id_usuario: int):
        """Cria o Atendimento, deriva o binário a partir do paciente e sincroniza a Consulta
        num único commit."""
        try:
            atendimento = Atendimento(
                id_consulta=consulta.id,
                tipo_atendimento=tipo_atendimento,
                realizado_por=id_usuario,
                status="em-andamento",
                data_hora_inicio=datetime.now(timezone.utc),
            )
            self.repo.save(atendimento, commit=False)
            # Deriva o binário do paciente (registros ativos x última conferência)
            # na mesma transação da abertura. Import local: ciclo de import.
            from .binario.binario_service import BinarioService
            BinarioService().derivar_na_abertura(atendimento, consulta.id_empresa)
            self._sincronizar(consulta, commit=False)
            self.repo.confirmar(commit=True)
            return atendimento
        except Exception:
            self.repo.rollback()
            raise

    # ------------------------------------------------------------- abertura
    def abrir_triagem(self, uuid_consulta: str, id_usuario: int, id_empresa: int):
        """
        Abre um Atendimento do tipo triagem para a Consulta.

        Pode haver várias triagens na mesma Consulta (ex.: retorno).

        Raises:
            RecursoNaoEncontradoError: Consulta inexistente ou de outra empresa.
            ConflictoError: Consulta encerrada; consentimento pendente; ou
                já há outro Atendimento em andamento.
        """
        return self._abrir(uuid_consulta, "triagem", id_usuario, id_empresa)

    def abrir_avaliacao_medica(self, uuid_consulta: str, id_usuario: int, id_empresa: int):
        """
        Abre um Atendimento do tipo avaliação médica para a Consulta.

        Não exige triagem prévia (a triagem é independente).

        Raises:
            RecursoNaoEncontradoError: Consulta inexistente ou de outra empresa.
            ConflictoError: Consulta encerrada; consentimento pendente; ou
                já há outro Atendimento em andamento.
        """
        return self._abrir(uuid_consulta, "avaliacao-medica", id_usuario, id_empresa)

    def abrir_reavaliacao(self, uuid_consulta: str, id_usuario: int, id_empresa: int):
        """
        Abre um Atendimento do tipo reavaliação (retorno do médico dentro do mesmo episódio).

        Só abre com a Consulta em STATUS_PARA_REAVALIACAO. A permissão de médico é
        aplicada no controller; a finalização também é só médico (TIPOS_SOMENTE_MEDICO).

        Raises:
            RecursoNaoEncontradoError: Consulta inexistente ou de outra empresa.
            ConflictoError: Consulta encerrada; consentimento pendente; já há outro
                Atendimento em andamento; ou a Consulta não está em em-observacao.
        """
        return self._abrir(uuid_consulta, "reavaliacao", id_usuario, id_empresa,
                           STATUS_PARA_REAVALIACAO)

    # ------------------------------------------------- finalizar / cancelar
    @staticmethod
    def _exigir_dono(atendimento, id_usuario: int, acao: str) -> None:
        """Só quem abriu o Atendimento o finaliza ou cancela (403)."""
        if atendimento.realizado_por != id_usuario:
            raise PermissaoNegadaError(
                f"Só o profissional que abriu o atendimento pode {acao}."
            )

    @staticmethod
    def _exigir_sem_pendencias_clinicas(atendimento) -> None:
        """Não deixa registro inconsistente para trás (409): avaliação da IA ainda processando ou
        prescrição em rascunho. O 'processando' que já passou do TTL é tarefa perdida e não bloqueia.
        Cancelar continua livre (abandonar não depende de nada); o rascunho que sobrar pode ser
        descartado depois (POST /prescricoes/<uuid>/descartar)."""
        # import local: avaliacao_bion depende deste módulo (ciclo de import)
        from src.domains.avaliacao_bion.service import TTL_PROCESSANDO
        from src.domains.avaliacao_bion.helpers.status import PROCESSANDO

        limite = datetime.now(timezone.utc) - TTL_PROCESSANDO
        for o in atendimento.outputs_bion:
            criado = o.criado_em
            if criado is not None and criado.tzinfo is None:
                criado = criado.replace(tzinfo=timezone.utc)
            if o.status == PROCESSANDO and (criado is None or criado >= limite):
                raise ConflictoError(
                    "A avaliação da IA ainda está em andamento: aguarde terminar antes de finalizar o atendimento."
                )
        if any(r.status == "rascunho" for r in atendimento.resultados_prescricao):
            raise ConflictoError(
                "Há uma prescrição em rascunho neste atendimento: confirme-a ou descarte-a antes de finalizar."
            )

    def finalizar(self, uuid_atendimento: str, id_empresa: int, id_usuario: int,
                  observacoes: str = None, eh_medico: bool = False):
        """
        Finaliza um Atendimento em andamento, registrando data/hora de
        término e observações opcionais do profissional. Sincroniza
        status_consulta na mesma transação.

        Só o dono (403). Exige o binário completo (409), em qualquer tipo de
        atendimento, e nenhuma pendência clínica (409): avaliação da IA processando
        ou prescrição em rascunho. `eh_medico` vem da sessão (controller): avaliação
        médica e reavaliação só são finalizadas por médico.

        Raises:
            RecursoNaoEncontradoError: Atendimento inexistente ou de outra empresa.
            PermissaoNegadaError: não é o dono; ou avaliação médica sem ser médico.
            ConflictoError: já finalizado; cancelado (ex: por evasão -- um
                Atendimento cancelado nunca vira finalizado); a Consulta já
                está encerrada; ou binário incompleto.
            DadosInvalidosError: observações que não são texto.
        """
        atendimento = self.buscar_por_uuid(uuid_atendimento, id_empresa)
        self._exigir_dono(atendimento, id_usuario, "finalizá-lo")
        if atendimento.tipo_atendimento in TIPOS_SOMENTE_MEDICO and not eh_medico:
            raise PermissaoNegadaError("Somente médico pode finalizar avaliação médica ou reavaliação.")
        if atendimento.status == "finalizado":
            raise ConflictoError("Atendimento já está finalizado.")
        if atendimento.status == "cancelado":
            raise ConflictoError("Atendimento cancelado não pode ser finalizado.")

        c = self.consulta_repo.find_by_id(atendimento.id_consulta)
        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta encerrada: o atendimento não pode mais ser finalizado.")

        exigir_binario_completo(atendimento)
        self._exigir_sem_pendencias_clinicas(atendimento)
        if observacoes is not None and not isinstance(observacoes, str):
            raise DadosInvalidosError("Observações inválidas.", erros={"observacoes": "deve ser texto."})

        try:
            # Reconcilia o binário com os registros ativos (dado inserido depois
            # pela rota granular) NA MESMA transação do finalizar. Import local:
            # BinarioService puxa os services de paciente (ciclo de import).
            from .binario.binario_service import BinarioService
            self.repo.travar(atendimento)
            BinarioService().reconciliar(atendimento, id_empresa)

            atendimento.status = "finalizado"
            atendimento.data_hora_fim = datetime.now(timezone.utc)
            if observacoes:
                atendimento.observacoes_profissional = observacoes
            self.repo.save(atendimento, commit=False)
            self._sincronizar(c, commit=False)
            self.repo.confirmar(commit=True)
            return atendimento
        except Exception:
            self.repo.rollback()
            raise

    def cancelar(self, uuid_atendimento: str, id_empresa: int, id_usuario: int,
                 motivo: str = None):
        """
        Cancela um Atendimento EM ANDAMENTO (aberto por engano, paciente saiu...).
        Sincroniza status_consulta na mesma transação.

        Só o dono (403). NÃO exige binário. `motivo` é opcional (None pula);
        se vier, precisa estar em MOTIVOS_CANCELAMENTO (422). Os dados
        clínicos já gravados neste atendimento permanecem (nada é apagado).

        Raises:
            RecursoNaoEncontradoError: Atendimento inexistente ou de outra empresa.
            PermissaoNegadaError: não é o dono.
            ConflictoError: o atendimento não está em andamento.
            DadosInvalidosError: motivo fora da lista.
        """
        atendimento = self.buscar_por_uuid(uuid_atendimento, id_empresa)
        self._exigir_dono(atendimento, id_usuario, "cancelá-lo")
        if atendimento.status != "em-andamento":
            raise ConflictoError(
                f"Só atendimento em andamento pode ser cancelado (status atual: {atendimento.status})."
            )
        if motivo is not None and motivo not in MOTIVOS_CANCELAMENTO:
            raise DadosInvalidosError(
                "Motivo de cancelamento inválido.",
                erros={"motivo_cancelamento": "inválido; use um de: " + ", ".join(MOTIVOS_CANCELAMENTO)},
            )

        c = self.consulta_repo.find_by_id(atendimento.id_consulta)
        try:
            atendimento.status = "cancelado"
            atendimento.data_hora_fim = datetime.now(timezone.utc)
            atendimento.motivo_cancelamento = motivo
            self.repo.save(atendimento, commit=False)
            self._sincronizar(c, commit=False)
            self.repo.confirmar(commit=True)
            return atendimento
        except Exception:
            self.repo.rollback()
            raise

    # ------------------------------------------------------- estatísticas
    def media_horas_ate_atendimento(self, id_empresa: int, dias: int = 30):
        """Média, em horas, entre o início dos sintomas e a busca por atendimento (None sem dados)."""
        return self.repo.media_horas_ate_atendimento(id_empresa=id_empresa, dias=dias)

    def tempo_medio_por_tipo(self, id_empresa: int, dias: int = 30):
        """Agregação bruta do repository (segundos, por tipo) nos últimos `dias`. A conversão
        para 'Xmin Ys' e a variação % vs. período anterior ficam na camada de estatística."""
        return self.repo.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)

    def atendimentos_por_status(self, id_empresa: int, dias: int = 30):
        """Contagem de Atendimentos por status nos últimos `dias`."""
        return self.repo.contar_atendimentos_por_status(id_empresa=id_empresa, dias=dias)

    def tempo_medio_por_tipo_periodo(self, id_empresa: int, data_inicio, data_fim):
        """Tempo médio por tipo com janela explícita [data_inicio, data_fim)."""
        return self.repo.tempo_medio_por_tipo_periodo(
            id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim
        )

    def tempo_medio_por_tipo_segmentado(self, id_empresa: int, dias: int = 30):
        """Tempo médio por tipo segmentado em 'mesmo_profissional' x 'transferencia' (ver o repository)."""
        return self.repo.tempo_medio_por_tipo_segmentado(id_empresa=id_empresa, dias=dias)
