"""Repositório de acesso a dados de ProtocoloEscoreConfig."""

from typing import Optional

from src.models import db
from src.core.interfaces import IRepository
from src.models.protocolos import ProtocoloEscoreConfig


class ProtocoloEscoreConfigRepository(IRepository[ProtocoloEscoreConfig]):
    """Encapsula todo acesso a dados de ProtocoloEscoreConfig via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[ProtocoloEscoreConfig]:
        return db.session.get(ProtocoloEscoreConfig, id)

    def find_by_protocolo_catalogo(self, id_protocolo_catalogo: int) -> Optional[ProtocoloEscoreConfig]:
        """Busca a config ativa vinculada a um protocolo_catalogo (relação 1:1)."""
        return ProtocoloEscoreConfig.query.filter_by(
            id_protocolo_catalogo=id_protocolo_catalogo, status="ativo"
        ).first()

    def save(self, entity: ProtocoloEscoreConfig) -> ProtocoloEscoreConfig:
        db.session.add(entity)
        db.session.commit()
        return entity