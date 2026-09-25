"""Repositório de leitura de ProtocoloVersao — resolve a versão vigente no momento da execução."""

from typing import Optional

from src.models import db
from src.core.interfaces import IRepository
from src.models.protocolos import ProtocoloVersao


class ProtocoloVersaoRepository(IRepository[ProtocoloVersao]):

    def find_by_id(self, id: int) -> Optional[ProtocoloVersao]:
        return db.session.get(ProtocoloVersao, id)

    def find_vigente(self, id_protocolo_catalogo: int) -> Optional[ProtocoloVersao]:
        """Busca a versão com status='ativa' para o protocolo. Assume que só
        existe uma ativa por vez (regra de negócio, não reforçada aqui por
        constraint de banco além do índice único id_protocolo_catalogo+numero_versao)."""
        return ProtocoloVersao.query.filter_by(
            id_protocolo_catalogo=id_protocolo_catalogo, status="ativa"
        ).first()