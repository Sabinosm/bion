"""Repositório de acesso a dados da entidade Consulta."""

from typing import Optional, List

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
