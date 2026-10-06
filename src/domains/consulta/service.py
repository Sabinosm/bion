"""Regras de negócio da entidade Consulta (Bloco 1)."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from .repository import ConsultaRepository

DESFECHOS_VALIDOS = ("alta", "internacao", "transferencia", "obito", "evasao")
ORIGENS_VALIDAS = ("espontanea", "SAMU", "transferencia", "regulacao")


class ConsultaService:
    """Abertura, consulta e encerramento de Consultas."""

    def __init__(self):
        self.repo = ConsultaRepository()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _paciente_svc():
        from src.domains.paciente.services import PacienteService
        return PacienteService()

    @staticmethod
    def _consentimento_svc():
        from src.domains.paciente.services.consentimento_service import ConsentimentoService
        return ConsentimentoService()

    def _barrar_se_aberta(self, id_paciente: int, id_empresa: int):
        aberta = self.repo.find_aberta_por_paciente(id_paciente, id_empresa)
        if aberta:
            raise ConflictoError(
                f"Paciente já possui consulta aberta: {aberta.uuid}. "
                "Continue nela (novo atendimento) ou encerre-a antes de abrir outra."
            )

    # ------------------------------------------------------------- leitura
    def buscar_por_uuid(self, uuid: str, id_empresa: int):
        """404 igual para 'não existe' e 'é de outra empresa'."""
        e = self.repo.find_by_uuid(uuid, id_empresa)
        if not e:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid}")
        return e

    def listar(self, id_empresa: int, apenas_abertas: bool = False):
        if apenas_abertas:
            return self.repo.find_abertas(id_empresa)
        return self.repo.find_all(id_empresa)

    def listar_por_paciente(self, uuid_paciente: str, id_empresa: int):
        paciente = self._paciente_svc().buscar_por_uuid(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(paciente.id, id_empresa)

    # --------------------------------------------------------------- abrir
    def abrir(self, dados: dict, id_usuario: int, id_empresa: int):
        """Abre uma Consulta, atomicamente (paciente + pessoais + consulta
        [+ dispensa de emergência] numa transação só). O corpo deve trazer
        EXATAMENTE UMA destas formas:

          {"uuid_paciente": "..."}                     paciente já cadastrado
          {"paciente": {...dados de cadastro...}}      cadastra e abre
          {"paciente_nao_identificado": true,          emergência sem cadastro
           "motivo_emergencia": "...",                 (obrigatório)
           "sexo_biologico": "M|F|I"}                  (opcional, padrão I)

        Opcional em todas: origem_encaminhamento.

        Emergência: o Paciente mínimo nasce com nao_identificado=True e o
        consentimento já nasce 'dispensado_emergencia'. Depois, o paciente
        é completado via PacienteService.identificar (sem duplicar).
        """
        origem = dados.get("origem_encaminhamento", "espontanea")
        if origem not in ORIGENS_VALIDAS:
            raise DadosInvalidosError(f"origem_encaminhamento inválida. Use um de: {', '.join(ORIGENS_VALIDAS)}")

        uuid_paciente = dados.get("uuid_paciente")
        novo = dados.get("paciente")
        sem_id = dados.get("paciente_nao_identificado") is True
        if sum(bool(x) for x in (uuid_paciente, novo, sem_id)) != 1:
            raise DadosInvalidosError(
                "Informe exatamente um de: uuid_paciente, paciente, paciente_nao_identificado."
            )

        pac_svc = self._paciente_svc()
        try:
            if uuid_paciente:
                paciente = pac_svc.buscar_por_uuid(uuid_paciente, id_empresa)
                self._barrar_se_aberta(paciente.id, id_empresa)
            elif novo:
                paciente = pac_svc.cadastrar(novo, id_usuario, id_empresa, commit=False)
            else:
                paciente = pac_svc.cadastrar_nao_identificado(
                    dados.get("sexo_biologico", "I"), id_usuario, id_empresa, commit=False
                )

            consulta = self.repo.nova(
                id_paciente=paciente.id,
                id_empresa=id_empresa,
                origem_encaminhamento=origem,
                iniciada_por=id_usuario,
            )
            try:
                self.repo.save(consulta, commit=False)   # flush: o índice único é checado aqui
            except IntegrityError:
                # uq_consulta_aberta_por_paciente: corrida entre duas aberturas.
                # O rollback (inclusive do paciente recém-cadastrado) é feito no except externo.
                raise ConflictoError("Paciente já possui consulta aberta.")

            if sem_id:
                self._consentimento_svc().dispensar_por_emergencia_id(
                    paciente.id, {"motivo": dados.get("motivo_emergencia")},
                    id_usuario, commit=False,
                )

            self.repo.confirmar(commit=True)   # único commit: paciente + consulta + consentimento
            return consulta
        except Exception:
            self.repo.rollback()
            raise

    # ----------------------------------------------------------- encerrar
    def _finalizar(self, c, desfecho: str, id_usuario: int, commit: bool, cancelar_pendentes: bool):
        from src.domains.atendimento.repository import AtendimentoRepository

        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta já está encerrada.")
        if desfecho not in DESFECHOS_VALIDOS:
            raise DadosInvalidosError(f"Desfecho inválido. Use um de: {', '.join(DESFECHOS_VALIDOS)}")

        pendentes = [a for a in AtendimentoRepository().find_por_consulta(c.id)
                     if a.status == "em-andamento"]
        if pendentes:
            if not cancelar_pendentes:
                raise ConflictoError(
                    "Existe Atendimento em andamento; finalize-o antes de encerrar a Consulta."
                )
            # data_hora_fim fica NULL de propósito: as estatísticas de tempo
            # médio filtram por data_hora_fim preenchida, e um atendimento
            # cancelado não pode entrar nessa média.
            for a in pendentes:
                a.status = "cancelado"

        c.status_consulta = "encerrada"
        c.desfecho_final = desfecho
        c.data_hora_fim = datetime.now(timezone.utc)
        c.finalizada_por = id_usuario
        return self.repo.save(c, commit=commit)

    def encerrar(self, uuid: str, desfecho: str, id_usuario: int, id_empresa: int, commit: bool = True):
        """Encerra com desfecho. Bloqueia se houver Atendimento em andamento."""
        c = self.buscar_por_uuid(uuid, id_empresa)
        return self._finalizar(c, desfecho, id_usuario, commit, cancelar_pendentes=False)

    def evadir(self, uuid: str, id_usuario: int, id_empresa: int, commit: bool = True):
        """Fluxo 2 (evasão): cancela Atendimentos em andamento e encerra."""
        c = self.buscar_por_uuid(uuid, id_empresa)
        return self._finalizar(c, "evasao", id_usuario, commit, cancelar_pendentes=True)

    # ------------------------------------------------------- consentimento
    def situacao_consentimento(self, uuid: str, id_empresa: int) -> dict:
        c = self.buscar_por_uuid(uuid, id_empresa)
        situacao = self._consentimento_svc().situacao(c.id_paciente, desde=c.data_hora_inicio)
        return {"valido": situacao is not None, "situacao": situacao}

    def exigir_consentimento(self, consulta):
        """GANCHO PARA O BLOCO 2: AtendimentoService chama isto antes de
        criar qualquer Atendimento. Lança ConflictoError se pendente."""
        self._consentimento_svc().exigir_valido(consulta.id_paciente, desde=consulta.data_hora_inicio)

    def registrar_consentimento(self, uuid: str, dados: dict, id_usuario: int, id_empresa: int):
        c = self.buscar_por_uuid(uuid, id_empresa)
        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta já está encerrada.")
        return self._consentimento_svc().registrar(c.paciente.uuid, dados, id_usuario, id_empresa)

    def dispensar_consentimento(self, uuid: str, dados: dict, id_usuario: int, id_empresa: int):
        c = self.buscar_por_uuid(uuid, id_empresa)
        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta já está encerrada.")
        return self._consentimento_svc().dispensar_por_emergencia(c.paciente.uuid, dados, id_usuario, id_empresa)

    # -------------------------------------------------------- estatísticas
    def contar_consultas_hoje(self, id_empresa):
        return self.repo.contar_consultas_hoje(id_empresa=id_empresa)

    def consultas_por_dia(self, id_empresa: int, dias: int = 30):
        return self.repo.contar_consultas_por_dia(id_empresa=id_empresa, dias=dias)

    def consultas_por_dia_periodo(self, id_empresa: int, data_inicio, data_fim):
        return self.repo.contar_consultas_por_dia_periodo(
            id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim
        )

    def consultas_por_status(self, id_empresa: int, dias: int = 30):
        return self.repo.contar_consultas_por_status(id_empresa=id_empresa, dias=dias)

    def consultas_por_status_periodo(self, id_empresa: int, data_inicio, data_fim):
        return self.repo.contar_consultas_por_status_periodo(
            id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim
        )