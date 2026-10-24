"""Regras de negócio da entidade Consulta (Bloco 1)."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from .repository import ConsultaRepository
from .paciente_resumo_service import bloco_paciente
from .filtros import validar_opcao, periodo_em_utc, montar_pagina
from .continuar_service import avaliar_continuidade, FUNCOES_CLINICAS
from src.models.clinico import Consulta
from .schema_consulta import DESFECHOS_VALIDOS, ORIGENS_VALIDAS
from src.domains.paciente.services.consentimento_service import consentimento_bloqueia_consulta

LIMITE_PADRAO_HISTORICO = 10
LIMITE_MAXIMO_HISTORICO = 50


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

    def listar_historico(self, id_empresa: int, id_usuario: int,
                         limit: int = LIMITE_PADRAO_HISTORICO, offset: int = 0, *,
                         status=None, desfecho=None, apenas_abertas: bool = False,
                         data_inicio=None, data_fim=None, funcao=None) -> dict:
        """Histórico paginado das Consultas iniciadas pelo profissional, da mais recente à mais antiga.

        Cada item vem com o bloco `paciente` e os campos de continuidade (`funcao` é a função
        clínica do usuário na sessão). Devolve a página: {itens, tem_mais, limit, offset,
        proximo_offset}. `limit` ausente ou menor que 1 usa o padrão; acima de LIMITE_MAXIMO_HISTORICO
        usa o teto; `offset` negativo vira 0. Sem resultado, `itens` é lista vazia (não é erro).

        Filtros opcionais: `status` (status_consulta), `desfecho` (desfecho_final), `apenas_abertas`,
        `data_inicio`/`data_fim` (AAAA-MM-DD no fuso da empresa, sobre o início da Consulta).
        Valor inválido levanta DadosInvalidosError (422).
        """
        if not limit or limit < 1:
            limit = LIMITE_PADRAO_HISTORICO
        limit = min(limit, LIMITE_MAXIMO_HISTORICO)
        offset = max(offset or 0, 0)

        status = validar_opcao(status, tuple(Consulta.status_consulta.type.enums), "status")
        desfecho = validar_opcao(desfecho, tuple(DESFECHOS_VALIDOS), "desfecho")
        inicio = fim = None
        if data_inicio or data_fim:
            inicio, fim = periodo_em_utc(data_inicio, data_fim, self.repo.fuso_da_empresa(id_empresa))

        brutos = self.repo.historico(
            id_empresa, id_usuario, limit=limit + 1, offset=offset, status=status,
            desfecho=desfecho, apenas_abertas=apenas_abertas, inicio=inicio, fim=fim,
        )
        pagina = brutos[:limit]
        em_andamento = self._em_andamento_por_consulta(pagina)
        itens = [self._com_continuidade(c, em_andamento.get(c.id), id_usuario, funcao) for c in pagina]
        return montar_pagina(itens, limit, offset, tem_mais=len(brutos) > limit)

    def _com_paciente(self, c) -> dict:
        """Consulta.to_dict() + bloco `paciente` (nome descriptografado).

        Nome é PII: só use em rota de médico/enfermeiro."""
        d = c.to_dict()
        d["paciente"] = bloco_paciente(c.paciente)
        return d

    @staticmethod
    def _em_andamento_por_consulta(consultas) -> dict:
        """{id_consulta: Atendimento em andamento} para as Consultas dadas, numa única query."""
        from src.domains.atendimento.repository import AtendimentoRepository
        return AtendimentoRepository().find_em_andamento_por_consultas([c.id for c in consultas])

    def _consentimento_pendente(self, c) -> bool:
        """True se a Consulta ainda não tem consentimento válido e a regra exige um para atender."""
        situacao = self._consentimento_svc().situacao(c.id_paciente, desde=c.data_hora_inicio)
        return situacao is None and consentimento_bloqueia_consulta()

    def _com_continuidade(self, c, atendimento_em_andamento, id_usuario: int, funcao) -> dict:
        """_com_paciente + pode_continuar, proxima_acao, acoes_disponiveis, atendimento_em_andamento
        e motivo_bloqueio (ver continuar_service.py). O consentimento só é consultado quando faz diferença:
        Consulta aberta, sem atendimento em andamento e usuário com função clínica."""
        pendente = (
            atendimento_em_andamento is None
            and c.status_consulta != "encerrada"
            and funcao in FUNCOES_CLINICAS
            and self._consentimento_pendente(c)
        )
        d = self._com_paciente(c)
        d.update(avaliar_continuidade(c, atendimento_em_andamento, id_usuario, funcao, pendente))
        return d

    def buscar_resumo(self, uuid: str, id_empresa: int, id_usuario: int = None, funcao=None) -> dict:
        """Detalhe da consulta já com o paciente (404 igual para 'não existe' e 'outra empresa').
        Com `id_usuario`, inclui os campos de continuidade (`funcao` = função clínica da sessão)."""
        c = self.buscar_por_uuid(uuid, id_empresa)
        if id_usuario is None:
            return self._com_paciente(c)
        em_andamento = self._em_andamento_por_consulta([c])
        return self._com_continuidade(c, em_andamento.get(c.id), id_usuario, funcao)

    def listar_resumo(self, id_empresa: int, apenas_abertas: bool = False) -> list[dict]:
        """Itens da lista: _com_paciente + `consentimento`. Só é
        calculado para consulta aberta; vale 'ativo' |
        'dispensado_emergencia' | 'pendente'. Custo: 1 a 2 queries por
        consulta aberta."""
        consentimento_svc = self._consentimento_svc()
        resultado = []
        for c in self.listar(id_empresa, apenas_abertas):
            d = self._com_paciente(c)
            if c.status_consulta == "encerrada":
                d["consentimento"] = None
            else:
                d["consentimento"] = (
                    consentimento_svc.situacao(c.id_paciente, desde=c.data_hora_inicio) or "pendente"
                )
            resultado.append(d)
        return resultado
    
    def listar_por_paciente(self, uuid_paciente: str, id_empresa: int, limit:bool):
        paciente = self._paciente_svc().buscar_por_uuid(uuid_paciente, id_empresa)
        if limit:
            return self.repo.find_por_paciente_limitado(paciente.id, id_empresa)
        else:
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
                paciente = pac_svc.buscar_valido(uuid_paciente, id_empresa)
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

        atendimento_repo = AtendimentoRepository()
        pendentes = [a for a in atendimento_repo.find_por_consulta(c.id)
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
                # salvamento explícito pelo repository (flush); o commit sai junto com a Consulta
                atendimento_repo.save(a, commit=False)

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
        return {
            "valido": situacao is not None,
            "situacao": situacao,
            "bloqueia_atendimento": situacao is None and consentimento_bloqueia_consulta(),
        }

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

    def consultas_por_desfecho(self, id_empresa: int, dias: int = 30):
        return self.repo.contar_consultas_por_desfecho(id_empresa=id_empresa, dias=dias)

    def consultas_por_desfecho_periodo(self, id_empresa: int, data_inicio, data_fim):
        return self.repo.contar_consultas_por_desfecho_periodo(
            id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim
        )