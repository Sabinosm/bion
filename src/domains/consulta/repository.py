"""Repositório de acesso a dados da entidade Consulta."""

from datetime import datetime, time, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Consulta
from src.models.corp.empresa import Empresa



class ConsultaRepository(IRepository[Consulta]):
    """Encapsula todo acesso a dados de Consulta via SQLAlchemy.

    TENANT: Consulta tem id_empresa próprio; toda busca por UUID e toda
    listagem exige id_empresa (da sessão). find_by_id é interno, para
    quem já validou a posse por outro caminho (ex: Atendimento.id_consulta).

    TRANSAÇÃO: commit/flush/rollback vivem aqui, nunca no service.
    save(commit=False) só faz flush, para o service compor várias
    escritas (paciente + consulta + consentimento, ou Atendimento +
    status da Consulta) num único commit.
    """

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        """Commit, ou só flush se o chamador vai comitar depois."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[Consulta]:
        """Busca pela chave primária. SEM filtro de empresa: só use com
        um id que já veio de um registro validado (ex: o id_consulta de
        um Atendimento da empresa)."""
        return db.session.get(Consulta, id)

    def find_by_uuid(self, uuid: str, id_empresa: int) -> Optional[Consulta]:
        return Consulta.query.filter_by(uuid=uuid, id_empresa=id_empresa).first()

    def find_por_paciente(self, id_paciente: int, id_empresa: int) -> List[Consulta]:
        return (Consulta.query
                .filter_by(id_paciente=id_paciente, id_empresa=id_empresa)
                .order_by(Consulta.data_hora_inicio.desc()).all())

    def find_abertas(self, id_empresa: int) -> List[Consulta]:
        return (Consulta.query.filter_by(id_empresa=id_empresa)
                .filter(Consulta.status_consulta != "encerrada").all())

    def find_all(self, id_empresa: int) -> List[Consulta]:
        return Consulta.query.filter_by(id_empresa=id_empresa).all()

    def find_aberta_por_paciente(self, id_paciente: int, id_empresa: int) -> Optional[Consulta]:
        return (Consulta.query.filter_by(id_paciente=id_paciente, id_empresa=id_empresa)
                .filter(Consulta.status_consulta != "encerrada").first())

    # --------------------------------------------------------------- escrita
    def nova(self, *, id_paciente, id_empresa, origem_encaminhamento, iniciada_por) -> Consulta:
        """Só instancia; quem controla a transação é o service."""
        return Consulta(id_paciente=id_paciente, id_empresa=id_empresa,
                        origem_encaminhamento=origem_encaminhamento,
                        status_consulta="aguardando-triagem",
                        data_hora_inicio=datetime.now(timezone.utc),
                        iniciada_por=iniciada_por)

    def save(self, entity: Consulta, commit: bool = True) -> Consulta:
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        """Consulta é registro clínico: não se apaga. Com
        cascade="all, delete-orphan" em Consulta.atendimentos, apagar uma
        Consulta levaria TODO o histórico clínico junto. Para encerrar
        use ConsultaService.encerrar/evadir. O método existe só para
        cumprir IRepository."""
        raise NotImplementedError(
            "Consulta não pode ser removida; encerre-a (ConsultaService.encerrar/evadir)."
        )

    # ---------------------------------------------------------- estatísticas
    def _empresa_e_offset(self, id_empresa: int):
        """Busca a Empresa e devolve (empresa, offset_str). offset_str
        é "+00:00" (UTC) se a empresa não existir ou não tiver UF
        resolvível -- ver Empresa.offset_horario.
        """
        empresa = db.session.get(Empresa, id_empresa)
        offset_str = empresa.offset_horario if empresa else "+00:00"
        return empresa, offset_str

    def _limites_do_dia_utc(self, id_empresa: int):
        """Calcula o início e o fim do dia de HOJE no fuso horário da
        empresa (ver Empresa.fuso_horario), já convertidos para UTC --
        necessário porque `data_hora_inicio` é gravado em UTC, então a
        comparação no banco precisa acontecer nesse mesmo referencial.
        """
        empresa, _ = self._empresa_e_offset(id_empresa)
        fuso = empresa.fuso_horario if empresa else timezone.utc

        agora_local = datetime.now(fuso)
        hoje_local = agora_local.date()

        inicio_local = datetime.combine(hoje_local, time.min, tzinfo=fuso)
        fim_local = datetime.combine(hoje_local, time.max, tzinfo=fuso)

        return inicio_local.astimezone(timezone.utc), fim_local.astimezone(timezone.utc)

    def contar_consultas_hoje(self, id_empresa: int) -> int:
        """"hoje" calculado no fuso da empresa (ver _limites_do_dia_utc),
        não em UTC direto.
        """
        inicio_dia, fim_dia = self._limites_do_dia_utc(id_empresa)

        return (
            db.session.query(func.count(Consulta.id))
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= inicio_dia)
            .filter(Consulta.data_hora_inicio <= fim_dia)
            .scalar() or 0
        )

    # --- A1: Volume de atendimentos (consultas) por dia ---
    def contar_consultas_por_dia(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Volume de Consultas iniciadas por dia, nos últimos N dias.

        O agrupamento por dia usa CONVERT_TZ() para converter
        `data_hora_inicio` (gravado em UTC) para o fuso da empresa ANTES
        de extrair a data -- sem isso, `func.date()` agrupa pelo dia em
        UTC, deslocando consultas de fim/início de dia local para o dia
        errado (ver Empresa.offset_horario).

        Retorna lista de dicts [{"data": date, "total": int}, ...]
        ordenada do dia mais antigo para o mais recente.
        """
        _, offset_str = self._empresa_e_offset(id_empresa)
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        dia_local = func.date(func.convert_tz(Consulta.data_hora_inicio, "+00:00", offset_str))

        linhas = (
            db.session.query(dia_local.label("data"), func.count(Consulta.id).label("total"))
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= limite)
            .group_by(dia_local)
            .order_by(dia_local.asc())
            .all()
        )
        return [{"data": linha.data, "total": linha.total} for linha in linhas]

    # --- A1 (comparação): consultas por dia, com janela explícita ---
    def contar_consultas_por_dia_periodo(self, id_empresa: int, data_inicio, data_fim) -> List[dict]:
        """Mesma agregação de contar_consultas_por_dia, mas com
        data_inicio/data_fim explícitos -- usado para o total do
        período ANTERIOR na comparação de A1. Mesmo ajuste de fuso.
        """
        _, offset_str = self._empresa_e_offset(id_empresa)
        dia_local = func.date(func.convert_tz(Consulta.data_hora_inicio, "+00:00", offset_str))

        linhas = (
            db.session.query(dia_local.label("data"), func.count(Consulta.id).label("total"))
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= data_inicio)
            .filter(Consulta.data_hora_inicio < data_fim)
            .group_by(dia_local)
            .order_by(dia_local.asc())
            .all()
        )
        return [{"data": linha.data, "total": linha.total} for linha in linhas]

    # --- A3: Taxa de conclusão vs. abandono ---
    def contar_consultas_por_status(self, id_empresa: int, dias: int = 30) -> dict:
        """Contagem de Consultas por status_consulta, nos últimos N dias.

        Retorna dict {status_consulta: total}, ex:
        {"encerrada": 130, "em-atendimento": 8, "em-triagem": 4, ...}
        Evasão NÃO é um status: é um desfecho_final de uma Consulta
        "encerrada". Para separar evasões de altas, agrupe por
        desfecho_final (não por status_consulta).
        Base para calcular a taxa de conclusão no service (contagem
        pura aqui; % é responsabilidade da camada de estatística).
        """
        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                Consulta.status_consulta.label("status"),
                func.count(Consulta.id).label("total"),
            )
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= limite)
            .group_by(Consulta.status_consulta)
            .all()
        )
        return {linha.status: linha.total for linha in linhas}

    # --- A3 (comparação): consultas por status, com janela explícita ---
    def contar_consultas_por_status_periodo(self, id_empresa: int, data_inicio, data_fim) -> dict:
        """Mesma agregação de contar_consultas_por_status, mas com
        data_inicio/data_fim explícitos -- usado para calcular o
        percentual do período ANTERIOR (comparação de A3).
        """
        linhas = (
            db.session.query(
                Consulta.status_consulta.label("status"),
                func.count(Consulta.id).label("total"),
            )
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= data_inicio)
            .filter(Consulta.data_hora_inicio < data_fim)
            .group_by(Consulta.status_consulta)
            .all()
        )
        return {linha.status: linha.total for linha in linhas}