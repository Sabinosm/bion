"""Repositório de acesso a dados da entidade Consulta."""

from datetime import datetime, time, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Consulta
from src.models.corp.empresa import Empresa



class ConsultaRepository(IRepository[Consulta]):
    """Encapsula todo acesso a dados de Consulta via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[Consulta]:
        """Busca uma Consulta pelo ID interno (chave primária)."""
        return db.session.get(Consulta, id)

    def find_by_uuid(self, uuid: str) -> Optional[Consulta]:
        """Busca uma Consulta pelo UUID público exposto na API."""
        return Consulta.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Consulta]:
        """Lista todas as Consultas de um paciente, mais recente primeiro."""
        return (
            Consulta.query
            .filter_by(id_paciente=id_paciente)
            .order_by(Consulta.data_hora_inicio.desc())
            .all()
        )

    def find_abertas(self) -> List[Consulta]:
        """Lista todas as Consultas que ainda não foram encerradas."""
        return Consulta.query.filter(Consulta.status_consulta != "encerrada").all()

    def save(self, entity: Consulta) -> Consulta:
        """Persiste (insert ou update) uma Consulta e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove uma Consulta pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[Consulta]:
        """Lista todas as Consultas cadastradas, sem filtro."""
        return Consulta.query.all()

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
        from src.models.usuarios.usuario import Usuario
        inicio_dia, fim_dia = self._limites_do_dia_utc(id_empresa)

        return (
            db.session.query(func.count(Consulta.id))
            .join(Usuario, Consulta.iniciada_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= inicio_dia)
            .filter(Consulta.data_hora_inicio <= fim_dia)
            .scalar() or 0
        )

    # --- A1: Volume de atendimentos (consultas) por dia ---
    def contar_consultas_por_dia(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Volume de Consultas iniciadas por dia, nos últimos N dias.

        ALTERADO: o agrupamento por dia agora usa CONVERT_TZ() para
        converter `data_hora_inicio` (gravado em UTC) para o fuso da
        empresa ANTES de extrair a data -- sem isso, `func.date()`
        agrupa pelo dia em UTC, deslocando consultas de fim/início de
        dia local para o dia errado (ver Empresa.offset_horario).

        Retorna lista de dicts [{"data": date, "total": int}, ...]
        ordenada do dia mais antigo para o mais recente.
        """
        from src.models.usuarios.usuario import Usuario

        _, offset_str = self._empresa_e_offset(id_empresa)
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        dia_local = func.date(func.convert_tz(Consulta.data_hora_inicio, "+00:00", offset_str))

        linhas = (
            db.session.query(dia_local.label("data"), func.count(Consulta.id).label("total"))
            .join(Usuario, Consulta.iniciada_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
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
        período ANTERIOR na comparação de A1.

        ALTERADO: mesmo ajuste de fuso de contar_consultas_por_dia.
        """
        from src.models.usuarios.usuario import Usuario

        _, offset_str = self._empresa_e_offset(id_empresa)
        dia_local = func.date(func.convert_tz(Consulta.data_hora_inicio, "+00:00", offset_str))

        linhas = (
            db.session.query(dia_local.label("data"), func.count(Consulta.id).label("total"))
            .join(Usuario, Consulta.iniciada_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
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
        {"encerrada": 130, "em-atendimento": 8, "evasao": 4, ...}
        Base para calcular a taxa de conclusão no service (contagem
        pura aqui; % é responsabilidade da camada de estatística).
        """
        from src.models.usuarios.usuario import Usuario

        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                Consulta.status_consulta.label("status"),
                func.count(Consulta.id).label("total"),
            )
            .join(Usuario, Consulta.iniciada_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
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
        from src.models.usuarios.usuario import Usuario

        linhas = (
            db.session.query(
                Consulta.status_consulta.label("status"),
                func.count(Consulta.id).label("total"),
            )
            .join(Usuario, Consulta.iniciada_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= data_inicio)
            .filter(Consulta.data_hora_inicio < data_fim)
            .group_by(Consulta.status_consulta)
            .all()
        )
        return {linha.status: linha.total for linha in linhas}