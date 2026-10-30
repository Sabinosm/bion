"""protocolo_versao_repository.py

Acesso de leitura às versões de protocolo (ProtocoloVersao). Resolve qual
versão está vigente no momento da execução, para que o cálculo e o registro
usem sempre a mesma versão.
"""
from typing import Optional

from src.core.interfaces import IRepository
from src.models import db
from src.models.protocolos import ProtocoloVersao


class ProtocoloVersaoRepository(IRepository[ProtocoloVersao]):

    def find_by_id(self, id: int) -> Optional[ProtocoloVersao]:
        return db.session.get(ProtocoloVersao, id)

    def find_vigente(self, id_protocolo_catalogo: int) -> Optional[ProtocoloVersao]:
        """Busca a versão com status='ativa' do protocolo.

        Assume uma única versão ativa por vez. Essa regra é de negócio e não
        é reforçada por constraint (o índice único cobre apenas
        id_protocolo_catalogo + numero_versao).
        """
        return ProtocoloVersao.query.filter_by(
            id_protocolo_catalogo=id_protocolo_catalogo, status="ativa"
        ).first()

    def save(self, entity: ProtocoloVersao):
        raise NotImplementedError("Versões de protocolo são criadas pelo seed, não por este repositório.")

    def delete(self, id: int):
        raise NotImplementedError("Versões de protocolo não são removidas por este repositório.")

    def find_by_uuid(self, uuid: str):
        raise NotImplementedError("ProtocoloVersao não é consultada por UUID.")
