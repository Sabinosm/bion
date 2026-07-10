"""Repositório de acesso a dados da entidade Atendimento."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Atendimento


class AtendimentoRepository(IRepository[Atendimento]):
    """Encapsula todo acesso a dados de Atendimento via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[Atendimento]:
        """Busca um Atendimento pelo ID interno (chave primária)."""
        return db.session.get(Atendimento, id)

    def find_by_uuid(self, uuid: str) -> Optional[Atendimento]:
        """Busca um Atendimento pelo UUID público exposto na API."""
        return Atendimento.query.filter_by(uuid=uuid).first()

    def find_por_consulta(self, id_consulta: int) -> List[Atendimento]:
        """Lista os Atendimentos de uma Consulta, em ordem cronológica."""
        return (
            Atendimento.query
            .filter_by(id_consulta=id_consulta)
            .order_by(Atendimento.data_hora_inicio.asc())
            .all()
        )

    def find_ultimo_por_tipo(self, id_consulta: int, tipo_atendimento: str) -> Optional[Atendimento]:
        """Retorna o Atendimento mais recente de um tipo específico dentro de uma Consulta."""
        return (
            Atendimento.query
            .filter_by(id_consulta=id_consulta, tipo_atendimento=tipo_atendimento)
            .order_by(Atendimento.data_hora_inicio.desc())
            .first()
        )

    def save(self, entity: Atendimento) -> Atendimento:
        """Persiste (insert ou update) um Atendimento e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um Atendimento pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[Atendimento]:
        """Lista todos os Atendimentos cadastrados, sem filtro."""
        return Atendimento.query.all()
