"""protocolo_escore_config_repository.py

Acesso a dados da configuração de escore ponderado (ProtocoloEscoreConfig),
usada pelo NEWS2 e por futuros escores por soma de parâmetros. A configuração
é vinculada ao protocolo do catálogo e não é versionada.
"""
from typing import Optional

from src.core.interfaces import IRepository
from src.models import db
from src.models.protocolos import ProtocoloEscoreConfig


class ProtocoloEscoreConfigRepository(IRepository[ProtocoloEscoreConfig]):

    def find_by_id(self, id: int) -> Optional[ProtocoloEscoreConfig]:
        return db.session.get(ProtocoloEscoreConfig, id)

    def find_by_protocolo_catalogo(self, id_protocolo_catalogo: int) -> Optional[ProtocoloEscoreConfig]:
        """Busca a configuração ativa do protocolo (relação 1:1)."""
        return ProtocoloEscoreConfig.query.filter_by(
            id_protocolo_catalogo=id_protocolo_catalogo, status="ativo"
        ).first()

    def save(self, entity: ProtocoloEscoreConfig) -> ProtocoloEscoreConfig:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int):
        raise NotImplementedError("Configurações de escore são criadas pelo seed, não removidas por este repositório.")

    def find_by_uuid(self, uuid: str):
        raise NotImplementedError("ProtocoloEscoreConfig não é consultada por UUID.")
