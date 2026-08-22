"""
ALTERADO: find_por_tipo não pode mais usar filter_by(tipo_regiao=...)
direto, já que tipo_regiao virou @property. Precisa de JOIN explícito
com TipoJurisdicao, filtrando pelo campo `codigo` (que guarda o mesmo
valor de string que o enum antigo usava: 'municipio', 'estado' etc).
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.corp import RegiaoGeografica
from src.models.corp.tipo_jurisdicao import TipoJurisdicao


class RegiaoRepository(IRepository[RegiaoGeografica]):

    def find_by_id(self, id: int) -> Optional[RegiaoGeografica]:
        return db.session.get(RegiaoGeografica, id)

    def find_by_uuid(self, uuid: str) -> Optional[RegiaoGeografica]:
        return RegiaoGeografica.query.filter_by(uuid=uuid).first()

    def find_by_codigo_ibge(self, codigo: str) -> Optional[RegiaoGeografica]:
        return RegiaoGeografica.query.filter_by(codigo_ibge=codigo).first()

    def find_por_tipo(self, tipo: str) -> List[RegiaoGeografica]:
        """`tipo` continua sendo a mesma string de antes (ex: 'municipio'),
        só a busca por baixo dos panos agora passa por TipoJurisdicao."""
        return (
            RegiaoGeografica.query
            .join(TipoJurisdicao, TipoJurisdicao.id == RegiaoGeografica.id_tipo_jurisdicao)
            .filter(TipoJurisdicao.codigo == tipo)
            .all()
        )
        
        
    def save(self, entity: RegiaoGeografica) -> RegiaoGeografica:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[RegiaoGeografica]:
        return RegiaoGeografica.query.all()