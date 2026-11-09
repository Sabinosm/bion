"""consentimento_service.py

Regras de negócio do consentimento LGPD do paciente: registro manual, revogação,
dispensa por emergência, a situação de consentimento (ponto de decisão para abrir
consulta) e o gate por escopo das finalidades opcionais (como o apoio de IA).

Este service NÃO toca em db.session: todo commit, flush e rollback é delegado ao
ConsentimentoRepository; aqui ficam só as regras e a mutação dos campos. Os
métodos de escrita aceitam `commit`: commit=False deixa pendente (flush) para o
chamador comitar junto com outras escritas (abrir consulta, registrar a assinatura
digital).

Há um PONTO ÚNICO de criação de consentimento ativo: qualquer fluxo (manual, QR
code, futuro portal) passa por ele, para que a regra "um ativo por paciente" seja a
mesma em todos (ele revoga os ativos anteriores, travando as linhas, e cria o novo).
A dispensa por emergência (LGPD art. 11, II, "f") não substitui nem revoga o
consentimento ativo. Dispensa só vale para a consulta cujo início é anterior a ela:
senão uma dispensa antiga liberaria todas as consultas futuras do paciente.

A regra "consulta x consentimento" tem uma chave única: por padrão NÃO bloqueia (a
consulta abre com ou sem consentimento, e a pendência é só sinalizada). Para voltar
a exigir, defina CONSENT_BLOQUEIA_CONSULTA=true no ambiente, sem mudar código.
Finalidades opcionais (IA etc.) seguem desligadas sem consentimento, independente
dessa chave: o gate por escopo falha fechado e consulta o banco a cada chamada,
então uma revogação vale na hora.
"""
import os
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from ..repositories import PacienteRepository, ConsentimentoRepository
from src.domains.paciente.schemas.schema_consentimento import (
    ConsentimentoCreateSchema, ConsentimentoDispensaEmergenciaSchema,
    ConsentimentoRevogarSchema,
)
from .comum import validar_schema, paciente_ou_404


def consentimento_bloqueia_consulta() -> bool:
    """Chave ÚNICA da regra "consulta x consentimento". Padrão: NÃO bloqueia (a consulta abre
    com ou sem consentimento). Para voltar a exigir, defina CONSENT_BLOQUEIA_CONSULTA=true no
    ambiente."""
    return os.getenv("CONSENT_BLOQUEIA_CONSULTA", "false").strip().lower() in ("1", "true", "sim", "yes")


class ConsentimentoService:

    def __init__(self):
        self.repo = ConsentimentoRepository()
        self.paciente_repo = PacienteRepository()

    def listar_por_paciente(self, uuid_paciente: str, id_empresa: int):
        """Histórico de consentimentos do paciente da empresa."""
        p = paciente_ou_404(self.paciente_repo, uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    # ------------------------------------------------------------------
    # PONTO ÚNICO de criação de consentimento ativo
    # ------------------------------------------------------------------
    def ativar_novo(
        self,
        id_paciente: int,
        *,
        coletado_por: int,
        versao_termo: str,
        canal_coleta: str,
        escopo=None,
        hash_documento: str = None,
        assinatura_png: bytes = None,
        data_consentimento=None,
        commit: bool = False,
    ):
        """Revoga TODOS os ativos anteriores do paciente e cria o novo. commit=False: só faz
        flush, e o chamador comita junto com o resto (ex.: fechar a sessão de assinatura na
        mesma transação).

        Raises:
            ConflictoError: outro consentimento ativo sendo registrado ao mesmo tempo (a UNIQUE
                de ativo único por paciente barrou a corrida).
        """
        from src.models.pacientes import Consentimento

        agora = datetime.now(timezone.utc)
        try:
            for antigo in self.repo.find_ativos_por_paciente(id_paciente, for_update=True):
                antigo.status = "revogado"
                antigo.data_revogacao = agora
                antigo.observacao = "Substituído por novo termo de consentimento."
                self.repo.save(antigo, commit=False)

            c = Consentimento(
                id_paciente=id_paciente,
                coletado_por=coletado_por,
                versao_termo=versao_termo,
                data_consentimento=data_consentimento or agora,
                canal_coleta=canal_coleta,
                escopo_consentimento_json=escopo,
                hash_documento=hash_documento,
                assinatura_png=assinatura_png,
            )
            return self.repo.save(c, commit=commit)
        except IntegrityError:
            # unique (id_paciente, ativo_unico) -- ver migração SQL
            self.repo.rollback()
            raise ConflictoError("Já existe um consentimento ativo sendo registrado para este paciente. Tente novamente.")

    def registrar(self, uuid_paciente: str, dados: dict, id_usuario_coletor: int, id_empresa: int,
                  commit: bool = True):
        """Registro manual. O canal 'presencial-digital' é rejeitado pelo ConsentimentoCreateSchema:
        só nasce do fluxo de assinatura por QR code.

        Raises:
            RecursoNaoEncontradoError: paciente inexistente na empresa.
            DadosInvalidosError: corpo inválido (erros por campo).
        """
        p = paciente_ou_404(self.paciente_repo, uuid_paciente, id_empresa)
        entrada = validar_schema(ConsentimentoCreateSchema, dados)

        return self.ativar_novo(
            p.id,
            coletado_por=id_usuario_coletor,
            versao_termo=entrada.versao_termo,
            canal_coleta=entrada.canal_coleta,
            escopo=entrada.escopo_consentimento,
            hash_documento=entrada.hash_documento,
            commit=commit,
        )

    def revogar(self, uuid_paciente: str, dados: dict, id_empresa: int, commit: bool = True):
        """Revoga o consentimento ativo, com motivo.

        Raises:
            RecursoNaoEncontradoError: paciente inexistente ou sem consentimento ativo.
            DadosInvalidosError: motivo inválido.
        """
        p = paciente_ou_404(self.paciente_repo, uuid_paciente, id_empresa)
        ativo = self.repo.find_ativo_por_paciente(p.id)
        if not ativo:
            raise RecursoNaoEncontradoError("Não há consentimento ativo para este paciente.")

        entrada = validar_schema(ConsentimentoRevogarSchema, dados)

        ativo.status = "revogado"
        ativo.data_revogacao = datetime.now(timezone.utc)
        ativo.observacao = entrada.motivo
        return self.repo.save(ativo, commit=commit)

    # ------------------------------------------------------------------
    # Dispensa por emergência (LGPD art. 11, II, "f")
    # ------------------------------------------------------------------
    def dispensar_por_emergencia(self, uuid_paciente: str, dados: dict, id_usuario: int,
                                 id_empresa: int, commit: bool = True):
        """Registra dispensa por urgência/emergência a partir do UUID do paciente (rota do
        médico/enfermeiro). Não substitui nem revoga consentimento ativo."""
        p = paciente_ou_404(self.paciente_repo, uuid_paciente, id_empresa)
        return self.dispensar_por_emergencia_id(p.id, dados, id_usuario, commit=commit)

    def dispensar_por_emergencia_id(self, id_paciente: int, dados: dict, id_usuario: int,
                                    commit: bool = True):
        """Mesma dispensa, a partir do id interno, para quem acabou de criar o paciente na mesma
        transação (ConsultaService.abrir, caso 'paciente não identificado'). `dados` exige
        `motivo`. Quem chama já é responsável pela posse do paciente (empresa).

        Raises:
            DadosInvalidosError: motivo ausente ou inválido.
        """
        from src.models.pacientes import Consentimento

        entrada = validar_schema(ConsentimentoDispensaEmergenciaSchema, dados)

        try:
            c = Consentimento(
                id_paciente=id_paciente,
                coletado_por=id_usuario,
                versao_termo="dispensa-emergencia",
                data_consentimento=datetime.now(timezone.utc),
                canal_coleta="dispensa-emergencia",
                status="dispensado_emergencia",
                observacao=entrada.motivo,
            )
            return self.repo.save(c, commit=commit)
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    # ------------------------------------------------------------------
    # Situação e gates
    # ------------------------------------------------------------------
    @staticmethod
    def _utc(dt):
        """MySQL costuma devolver datetime naive; assume UTC (como gravamos)."""
        return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def situacao(self, id_paciente: int, desde=None):
        """'ativo' | 'dispensado_emergencia' | None.

        Consentimento ativo vale sempre. Dispensa de emergência só vale se registrada A PARTIR do
        início da consulta (`desde`); senão uma dispensa antiga liberaria TODAS as consultas
        futuras do paciente."""
        if self.repo.find_ativo_por_paciente(id_paciente):
            return "ativo"
        desde = self._utc(desde)
        for c in self.repo.find_por_paciente(id_paciente):
            if c.status == "dispensado_emergencia" and (
                desde is None or self._utc(c.data_consentimento) >= desde
            ):
                return "dispensado_emergencia"
        return None

    def exigir_valido(self, id_paciente: int, desde=None):
        """Devolve a situação ('ativo' | 'dispensado_emergencia' | None). None = ciência pendente
        (o paciente ainda não assinou nem foi dispensado).

        Raises:
            ConflictoError: só se CONSENT_BLOQUEIA_CONSULTA estiver ligado e a situação for None;
                com o padrão (desligado) quem chama pode ignorar o retorno ou usá-lo para sinalizar
                a pendência.
        """
        situacao = self.situacao(id_paciente, desde)
        if situacao is None and consentimento_bloqueia_consulta():
            raise ConflictoError(
                "Consentimento LGPD pendente: colete o termo ou registre a dispensa por emergência."
            )
        return situacao

    def escopo_permitido(self, id_paciente: int, escopo: str) -> bool:
        """True só se há consentimento ATIVO que inclui `escopo`. Falha fechada: sem consentimento,
        recusa, revogação, dispensa por emergência ou JSON fora do formato => False. Consulta o
        banco a cada chamada (sem cache), então uma revogação vale na hora.

        Uso: `if not ConsentimentoService().escopo_permitido(id_paciente, "apoio_ia"): ...`"""
        ativo = self.repo.find_ativo_por_paciente(id_paciente)
        if not ativo or not isinstance(ativo.escopo_consentimento_json, dict):
            return False
        escopos = ativo.escopo_consentimento_json.get("escopo")
        return isinstance(escopos, list) and escopo in escopos
