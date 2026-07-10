"""Repositório de acesso a dados da entidade CatalogoModulos."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.protocolos import CatalogoModulos


class CatalogoModulosRepository(IRepository[CatalogoModulos]):
    """Encapsula todo acesso a dados de CatalogoModulos via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[CatalogoModulos]:
        """Busca um CatalogoModulos pelo ID interno (chave primária)."""
        return db.session.get(CatalogoModulos, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoModulos]:
        """Busca um CatalogoModulos pelo UUID público exposto na API."""
        return CatalogoModulos.query.filter_by(uuid=uuid).first()

    def save(self, entity: CatalogoModulos) -> CatalogoModulos:
        """Persiste (insert ou update) um CatalogoModulos e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um CatalogoModulos pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[CatalogoModulos]:
        """Lista todos os CatalogoModulos cadastrados, sem filtro."""
        return CatalogoModulos.query.all()
