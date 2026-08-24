"""Repositório de acesso a dados da entidade Consulta."""

from datetime import datetime, time, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Consulta



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
    
    def contar_consultas_hoje(self, id_empresa: int) -> int:
        from src.models.usuarios.usuario import Usuario
        hoje = datetime.now(timezone.utc).date()
        inicio_dia = datetime.combine(hoje, time.min, tzinfo=timezone.utc)
        fim_dia = datetime.combine(hoje, time.max, tzinfo=timezone.utc)

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

        Retorna lista de dicts [{"data": date, "total": int}, ...]
        ordenada do dia mais antigo para o mais recente.
        """
        from src.models.usuarios.usuario import Usuario

        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        dia = func.date(Consulta.data_hora_inicio)

        linhas = (
            db.session.query(dia.label("data"), func.count(Consulta.id).label("total"))
            .join(Usuario, Consulta.iniciada_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(Consulta.data_hora_inicio >= limite)
            .group_by(dia)
            .order_by(dia.asc())
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
