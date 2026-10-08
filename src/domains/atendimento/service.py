"""Regras de negócio do ciclo de vida do Atendimento (abertura e finalização).

LIGAÇÃO COM O BLOCO 1 (Consulta):
  - Tenant: Atendimento não tem id_empresa próprio; a posse vem da Consulta
    (Consulta.id_empresa). Toda busca passa por id_empresa da sessão, e
    "não existe" e "é de outra empresa" dão o mesmo 404.
  - Consentimento: abrir qualquer Atendimento exige consentimento LGPD
    válido (ativo ou dispensado por emergência nesta consulta) -- ver
    ConsultaService.exigir_consentimento.
  - Consulta encerrada (inclusive por evasão) não aceita novo Atendimento
    nem finalização de Atendimento.
  - Transação: criar/finalizar o Atendimento e recalcular o status da
    Consulta é UMA operação atômica (um único commit, no repository).
"""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, PermissaoNegadaError
from .repository import AtendimentoRepository
from src.domains.consulta.repository import ConsultaRepository
from src.domains.consulta.service import ConsultaService
from src.domains.consulta.status_sync import sincronizar_status_consulta


class AtendimentoService:
    """Casos de uso relacionados à abertura, consulta e finalização de Atendimentos.

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

    def listar(self, id_empresa: int):
        """Lista os Atendimentos da empresa."""
        return self.repo.find_all(id_empresa)

    def listar_por_consulta(self, uuid_consulta: str, id_empresa: int):
        """Lista os Atendimentos de uma Consulta da empresa. A posse é
        checada na Consulta; find_por_consulta em si não filtra empresa."""
        c = self.consulta_svc.buscar_por_uuid(uuid_consulta, id_empresa)
        return self.repo.find_por_consulta(c.id)

    # -------------------------------------------------------- transação
    def _sincronizar(self, consulta, commit: bool):
        """Recalcula status_consulta a partir dos Atendimentos atuais.
        Com commit=False fica pendente, junto com a escrita do Atendimento."""
        atendimentos = self.repo.find_por_consulta(consulta.id)
        sincronizar_status_consulta(consulta, atendimentos)
        self.consulta_repo.save(consulta, commit=commit)

    def _consulta_para_abrir(self, uuid_consulta: str, id_empresa: int):
        """Consulta da empresa, não encerrada e com consentimento válido."""
        c = self.consulta_svc.buscar_por_uuid(uuid_consulta, id_empresa)
        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta encerrada: não é possível abrir novo atendimento.")
        # GANCHO DO BLOCO 1: lança ConflictoError se o consentimento está pendente.
        self.consulta_svc.exigir_consentimento(c)
        return c

    def _exigir_sem_em_andamento(self, consulta):
        """Um Atendimento em andamento por vez na Consulta."""
        if any(a.status == "em-andamento" for a in self.repo.find_por_consulta(consulta.id)):
            raise ConflictoError(
                "Já existe um atendimento em andamento nesta Consulta: finalize-o antes de abrir outro."
            )

    def _criar(self, consulta, tipo_atendimento: str, id_usuario: int):
        """Cria o Atendimento e sincroniza a Consulta num único commit."""
        from src.models.clinico import Atendimento
        try:
            atendimento = Atendimento(
                id_consulta=consulta.id,
                tipo_atendimento=tipo_atendimento,
                realizado_por=id_usuario,
                status="em-andamento",
                data_hora_inicio=datetime.now(timezone.utc),
            )
            self.repo.save(atendimento, commit=False)
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
        c = self._consulta_para_abrir(uuid_consulta, id_empresa)
        self._exigir_sem_em_andamento(c)
        return self._criar(c, "triagem", id_usuario)

    def abrir_avaliacao_medica(self, uuid_consulta: str, id_usuario: int, id_empresa: int):
        """
        Abre um Atendimento do tipo avaliação médica para a Consulta.

        Não exige triagem prévia (a triagem é independente).

        Raises:
            RecursoNaoEncontradoError: Consulta inexistente ou de outra empresa.
            ConflictoError: Consulta encerrada; consentimento pendente; ou
                já há outro Atendimento em andamento.
        """
        c = self._consulta_para_abrir(uuid_consulta, id_empresa)
        self._exigir_sem_em_andamento(c)
        return self._criar(c, "avaliacao-medica", id_usuario)

    # ------------------------------------------------------------ finalizar
    def finalizar(self, uuid_atendimento: str, id_empresa: int, observacoes: str = None,
                  eh_medico: bool = False):
        """
        Finaliza um Atendimento em andamento, registrando data/hora de
        término e observações opcionais do profissional. Sincroniza
        status_consulta na mesma transação.

        `eh_medico` vem da sessão (controller): triagem pode ser finalizada
        por enfermeiro ou médico, mas avaliação médica só por médico.

        Raises:
            RecursoNaoEncontradoError: Atendimento inexistente ou de outra empresa.
            PermissaoNegadaError: avaliação médica finalizada por quem não é médico.
            ConflictoError: já finalizado; cancelado (ex: por evasão -- um
                Atendimento cancelado nunca vira finalizado); ou a
                Consulta já está encerrada.
        """
        atendimento = self.buscar_por_uuid(uuid_atendimento, id_empresa)
        if atendimento.tipo_atendimento == "avaliacao-medica" and not eh_medico:
            raise PermissaoNegadaError("Somente médico pode finalizar uma avaliação médica.")
        if atendimento.status == "finalizado":
            raise ConflictoError("Atendimento já está finalizado.")
        if atendimento.status == "cancelado":
            raise ConflictoError("Atendimento cancelado não pode ser finalizado.")

        c = self.consulta_repo.find_by_id(atendimento.id_consulta)
        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta encerrada: o atendimento não pode mais ser finalizado.")

        try:
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

    # ------------------------------------------------------- estatísticas
    # --- C4: Tempo até busca por atendimento ---
    def media_horas_ate_atendimento(self, id_empresa: int, dias: int = 30):
        return self.repo.media_horas_ate_atendimento(id_empresa=id_empresa, dias=dias)

    # --- A2: Tempo médio de atendimento, por tipo ---
    def tempo_medio_por_tipo(self, id_empresa: int, dias: int = 30):
        """Repassa a agregação bruta do repository (segundos, por tipo).
        Conversão para 'Xmin Ys' e variação % vs. período anterior ficam
        na camada de estatística."""
        return self.repo.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)

    # --- auxiliar: status no nível de etapa (não usado na Fase 1, mas pronto) ---
    def atendimentos_por_status(self, id_empresa: int, dias: int = 30):
        return self.repo.contar_atendimentos_por_status(id_empresa=id_empresa, dias=dias)

    # --- E2: tempo médio por tipo, com janela explícita ---
    def tempo_medio_por_tipo_periodo(self, id_empresa: int, data_inicio, data_fim):
        return self.repo.tempo_medio_por_tipo_periodo(
            id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim
        )

    # --- Validação: tempo médio por tipo, segmentado mesmo-profissional
    #     vs. transferência entre profissionais (ver repository para o
    #     motivo -- médico sozinho fazendo triagem+avaliação distorce a
    #     média combinada de A2/E2 se não for segmentado) ---
    def tempo_medio_por_tipo_segmentado(self, id_empresa: int, dias: int = 30):
        return self.repo.tempo_medio_por_tipo_segmentado(id_empresa=id_empresa, dias=dias)