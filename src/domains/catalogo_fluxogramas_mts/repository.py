"""Repositório de acesso a dados da entidade CatalogoFluxogramasMts."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.protocolos import CatalogoFluxogramasMts


class CatalogoFluxogramasMtsRepository(IRepository[CatalogoFluxogramasMts]):
    """Encapsula todo acesso a dados de CatalogoFluxogramasMts via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[CatalogoFluxogramasMts]:
        """Busca um CatalogoFluxogramasMts pelo ID interno (chave primária)."""
        return db.session.get(CatalogoFluxogramasMts, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoFluxogramasMts]:
        """Busca um CatalogoFluxogramasMts pelo UUID público exposto na API."""
        return CatalogoFluxogramasMts.query.filter_by(uuid=uuid).first()

    def save(self, entity: CatalogoFluxogramasMts) -> CatalogoFluxogramasMts:
        """Persiste (insert ou update) um CatalogoFluxogramasMts e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um CatalogoFluxogramasMts pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[CatalogoFluxogramasMts]:
        """Lista todos os CatalogoFluxogramasMts cadastrados, sem filtro."""
        return CatalogoFluxogramasMts.query.all()
