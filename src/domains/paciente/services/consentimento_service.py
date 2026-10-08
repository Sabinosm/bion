from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, ConsentimentoRepository
from src.domains.paciente.schemas.schema_consentimento import (
    ConsentimentoCreateSchema, ConsentimentoDispensaEmergenciaSchema,
    ConsentimentoRevogarSchema, erros_pydantic_por_campo,
)


class ConsentimentoService:
    """Consentimento LGPD do paciente.

    TRANSAÇÃO: este service NÃO toca em db.session. Todo commit, flush e
    rollback é delegado ao ConsentimentoRepository (`save`, `confirmar`,
    `rollback`); aqui só ficam as regras e a mutação dos campos.

    Os métodos de escrita aceitam `commit`: commit=False deixa pendente
    (flush) para o chamador comitar junto com outras escritas
    (ConsultaService.abrir, ConsentimentoDigitalService.registrar_assinatura).
    """

    def __init__(self):
        self.repo = ConsentimentoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_por_paciente(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    # ------------------------------------------------------------------
    # PONTO ÚNICO de criação de consentimento ativo.
    # Qualquer fluxo (manual, QR code, futuro portal) passa por aqui, para
    # que a regra "um ativo por paciente" seja a mesma em todos.
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
        pdf_final_path: str = None,
        assinatura_imagem_path: str = None,
        commit: bool = False,
    ):
        """Revoga TODOS os ativos anteriores do paciente e cria o novo.
        commit=False: só faz flush -- o chamador comita junto com o resto
        (ex.: fechar a sessão de assinatura na mesma transação)."""
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
                data_consentimento=agora,
                canal_coleta=canal_coleta,
                escopo_consentimento_json=escopo,
                hash_documento=hash_documento,
                pdf_final_path=pdf_final_path,
                assinatura_imagem_path=assinatura_imagem_path,
            )
            return self.repo.save(c, commit=commit)
        except IntegrityError:
            # unique (id_paciente, ativo_unico) -- ver migração SQL
            self.repo.rollback()
            raise ConflictoError("Já existe um consentimento ativo sendo registrado para este paciente. Tente novamente.")

    def registrar(self, uuid_paciente: str, dados: dict, id_usuario_coletor: int, id_empresa: int,
                  commit: bool = True):
        """Registro manual. O canal 'presencial-digital' é rejeitado pelo
        ConsentimentoCreateSchema: só nasce do fluxo de assinatura por QR code."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)

        try:
            entrada = ConsentimentoCreateSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

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
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        ativo = self.repo.find_ativo_por_paciente(p.id)
        if not ativo:
            raise RecursoNaoEncontradoError("Não há consentimento ativo para este paciente.")

        try:
            entrada = ConsentimentoRevogarSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        ativo.status = "revogado"
        ativo.data_revogacao = datetime.now(timezone.utc)
        ativo.observacao = entrada.motivo
        return self.repo.save(ativo, commit=commit)

    # ------------------------------------------------------------------
    # Dispensa por emergência (LGPD art. 11, II, "f")
    # ------------------------------------------------------------------
    def dispensar_por_emergencia(self, uuid_paciente: str, dados: dict, id_usuario: int,
                                 id_empresa: int, commit: bool = True):
        """Registra dispensa por urgência/emergência a partir do UUID do
        paciente (rota do médico/enfermeiro). Não substitui nem revoga
        consentimento ativo."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.dispensar_por_emergencia_id(p.id, dados, id_usuario, commit=commit)

    def dispensar_por_emergencia_id(self, id_paciente: int, dados: dict, id_usuario: int,
                                    commit: bool = True):
        """Mesma dispensa, a partir do id interno -- para quem acabou de
        criar o paciente na mesma transação (ConsultaService.abrir, caso
        'paciente não identificado'). `dados` exige `motivo`. Quem chama
        já é responsável pela posse do paciente (empresa)."""
        from src.models.pacientes import Consentimento

        try:
            entrada = ConsentimentoDispensaEmergenciaSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

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
    # Gancho do Bloco 2: o Atendimento só abre com consentimento válido.
    # ------------------------------------------------------------------
    @staticmethod
    def _utc(dt):
        """MySQL costuma devolver datetime naive; assume UTC (como gravamos)."""
        return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def situacao(self, id_paciente: int, desde=None):
        """'ativo' | 'dispensado_emergencia' | None.

        Consentimento ativo vale sempre. Dispensa de emergência só vale se
        registrada A PARTIR do início da consulta (`desde`); senão uma
        dispensa antiga liberaria TODAS as consultas futuras do paciente."""
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
        """Lança ConflictoError (409) se não há consentimento válido."""
        if self.situacao(id_paciente, desde) is None:
            raise ConflictoError(
                "Consentimento LGPD pendente: colete o termo ou registre a dispensa por emergência."
            )