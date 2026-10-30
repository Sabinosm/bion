"""protocolo_catalogo_repository.py

Acesso a dados do catálogo de protocolos (ProtocoloCatalogo). Concentra as
consultas de cadastro e as listagens do catálogo, incluindo as que cruzam o
protocolo com o status de liberação da empresa.
"""
from typing import List, Optional

from sqlalchemy import or_

from src.core.interfaces import IRepository
from src.models import db
from src.models.protocolos import ProtocoloCatalogo

TAMANHO_PAGINA = 20


class ProtocoloCatalogoRepository(IRepository[ProtocoloCatalogo]):

    def find_by_id(self, id: int) -> Optional[ProtocoloCatalogo]:
        """Busca pelo ID interno (chave primária)."""
        return db.session.get(ProtocoloCatalogo, id)

    def find_by_uuid(self, uuid: str) -> Optional[ProtocoloCatalogo]:
        """Busca pelo UUID público exposto na API."""
        return ProtocoloCatalogo.query.filter_by(uuid=uuid).first()

    def find_by_sigla(self, sigla: str) -> Optional[ProtocoloCatalogo]:
        """Busca pela sigla (ex.: 'MTS', 'NEWS2')."""
        return ProtocoloCatalogo.query.filter_by(sigla=sigla).first()

    def find_all(self) -> List[ProtocoloCatalogo]:
        """Lista todos os protocolos cadastrados, sem filtro."""
        return ProtocoloCatalogo.query.all()

    def save(self, entity: ProtocoloCatalogo) -> ProtocoloCatalogo:
        """Persiste (insert ou update) e confirma a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all_com_status_empresa(self, id_empresa: int):
        """Lista os protocolos ativos com o status de liberação da empresa.

        Retorna linhas (ProtocoloCatalogo, ativo, politica). Protocolo nunca
        tocado pela empresa aparece com ativo/politica None, em vez de sumir.
        """
        return self._query_com_status_empresa(id_empresa).all()

    def find_all_filtrado(
        self,
        id_empresa: int,
        tipo_protocolo: str = None,
        escopo_populacao: str = None,
        escopo_uso: str = None,
        apenas_liberados: bool = False,
        offset: int = 0,
    ):
        """Igual a `find_all_com_status_empresa`, com filtros e paginação.

        `escopo_uso` casa o valor informado ou 'ambos'. `apenas_liberados`
        mantém só os protocolos ativos para a empresa. Ordena por ID para que a
        paginação seja estável e devolve no máximo TAMANHO_PAGINA linhas a
        partir de `offset` (valores negativos valem 0).
        """
        from src.models.corp import EmpresaProtocolo

        query = self._query_com_status_empresa(id_empresa)

        if tipo_protocolo:
            query = query.filter(ProtocoloCatalogo.tipo_protocolo == tipo_protocolo)
        if escopo_populacao:
            query = query.filter(ProtocoloCatalogo.escopo_populacao == escopo_populacao)
        if escopo_uso:
            query = query.filter(self._filtro_escopo_uso(escopo_uso))
        if apenas_liberados:
            query = query.filter(EmpresaProtocolo.ativo.is_(True))

        return query.offset(max(offset, 0)).limit(TAMANHO_PAGINA).all()

    def find_ativos_para_escopo(self, escopo: str) -> List[ProtocoloCatalogo]:
        """Lista os protocolos ativos cujo escopo de uso é o informado, 'ambos' ou não definido."""
        q = ProtocoloCatalogo.query.filter_by(status="ativo")
        return q.filter(self._filtro_escopo_uso(escopo)).all()

    @staticmethod
    def _filtro_escopo_uso(escopo: str):
        """Protocolo serve ao escopo se for o informado, 'ambos' ou não definido (NULL).
        Regra única das listagens, para que não divirjam."""
        return or_(
            ProtocoloCatalogo.escopo_uso.is_(None),
            ProtocoloCatalogo.escopo_uso == "ambos",
            ProtocoloCatalogo.escopo_uso == escopo,
        )

    @staticmethod
    def _query_com_status_empresa(id_empresa: int):
        """Base das listagens: protocolos ativos com LEFT JOIN em EmpresaProtocolo."""
        from src.models.corp import EmpresaProtocolo

        return (
            ProtocoloCatalogo.query
            .outerjoin(
                EmpresaProtocolo,
                (EmpresaProtocolo.id_protocolo_catalogo == ProtocoloCatalogo.id) &
                (EmpresaProtocolo.id_empresa == id_empresa),
            )
            .add_columns(EmpresaProtocolo.ativo, EmpresaProtocolo.politica)
            .filter(ProtocoloCatalogo.status == "ativo")
            .order_by(ProtocoloCatalogo.id)
        )
