"""Repositório de acesso a dados da entidade ProtocoloCatalogo."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.protocolos import ProtocoloCatalogo


class ProtocoloCatalogoRepository(IRepository[ProtocoloCatalogo]):
    """Encapsula todo acesso a dados de ProtocoloCatalogo via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[ProtocoloCatalogo]:
        """Busca um ProtocoloCatalogo pelo ID interno (chave primária)."""
        return db.session.get(ProtocoloCatalogo, id)

    def find_by_uuid(self, uuid: str) -> Optional[ProtocoloCatalogo]:
        """Busca um ProtocoloCatalogo pelo UUID público exposto na API."""
        return ProtocoloCatalogo.query.filter_by(uuid=uuid).first()

    def find_by_sigla(self, sigla: str) -> Optional[ProtocoloCatalogo]:
        """Busca um ProtocoloCatalogo pela sigla (ex: 'MTS', 'NEWS2')."""
        return ProtocoloCatalogo.query.filter_by(sigla=sigla).first()

    def save(self, entity: ProtocoloCatalogo) -> ProtocoloCatalogo:
        """Persiste (insert ou update) um ProtocoloCatalogo e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um ProtocoloCatalogo pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[ProtocoloCatalogo]:
        """Lista todos os ProtocoloCatalogo cadastrados, sem filtro."""
        return ProtocoloCatalogo.query.all()
