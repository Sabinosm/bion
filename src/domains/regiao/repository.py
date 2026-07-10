from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.corp import RegiaoGeografica


class RegiaoRepository(IRepository[RegiaoGeografica]):

    def find_by_id(self, id: int) -> Optional[RegiaoGeografica]:
        return db.session.get(RegiaoGeografica, id)

    def find_by_uuid(self, uuid: str) -> Optional[RegiaoGeografica]:
        return RegiaoGeografica.query.filter_by(uuid=uuid).first()

    def find_by_codigo_ibge(self, codigo: str) -> Optional[RegiaoGeografica]:
        return RegiaoGeografica.query.filter_by(codigo_ibge=codigo).first()

    def find_por_tipo(self, tipo: str) -> List[RegiaoGeografica]:
        return RegiaoGeografica.query.filter_by(tipo_regiao=tipo).all()

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
