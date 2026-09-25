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
    # shared/repositories/protocolo_catalogo_repository.py — método novo

    def find_all_com_status_empresa(self, id_empresa: int):
        """Lista todo o catálogo, com um LEFT JOIN em EmpresaProtocolo para
        trazer o status de liberação junto -- protocolo nunca tocado pela
        empresa aparece com vinculo=None, não fica ausente da lista."""
        from src.models.protocolos import EmpresaProtocolo
        return (
            ProtocoloCatalogo.query
            .outerjoin(
                EmpresaProtocolo,
                (EmpresaProtocolo.id_protocolo_catalogo == ProtocoloCatalogo.id) &
                (EmpresaProtocolo.id_empresa == id_empresa),
            )
            .add_columns(EmpresaProtocolo.ativo, EmpresaProtocolo.politica)
            .filter(ProtocoloCatalogo.status == "ativo")
            .all()
        )
    # shared/repositories/protocolo_catalogo_repository.py — método novo

    def find_all_filtrado(
        self,
        id_empresa: int,
        tipo_protocolo: str = None,
        escopo_populacao: str = None,
        escopo_uso: str = None,
        apenas_liberados: bool = False,
        offset: int = 0,
    ):
        from src.models.protocolos import EmpresaProtocolo

        query = (
            ProtocoloCatalogo.query
            .outerjoin(
                EmpresaProtocolo,
                (EmpresaProtocolo.id_protocolo_catalogo == ProtocoloCatalogo.id) &
                (EmpresaProtocolo.id_empresa == id_empresa),
            )
            .add_columns(EmpresaProtocolo.ativo, EmpresaProtocolo.politica)
            .filter(ProtocoloCatalogo.status == "ativo")
        )

        if tipo_protocolo:
            query = query.filter(ProtocoloCatalogo.tipo_protocolo == tipo_protocolo)
        if escopo_populacao:
            query = query.filter(ProtocoloCatalogo.escopo_populacao == escopo_populacao)
        if escopo_uso:
            query = query.filter(
                (ProtocoloCatalogo.escopo_uso == escopo_uso) | (ProtocoloCatalogo.escopo_uso == "ambos")
            )
        if apenas_liberados:
            query = query.filter(EmpresaProtocolo.ativo == True)

        return query.offset(offset).limit(20).all()