from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.catalogo_exames import CatalogoExames

class CatalogoExamesRepository(IRepository[CatalogoExames]):

    def find_by_id(self, id: int) -> Optional[CatalogoExames]:
        return db.session.get(CatalogoExames, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoExames]:
        return CatalogoExames.query.filter_by(uuid=uuid).first()

    def buscar_por_nome(self, termo: str) -> List[CatalogoExames]:
        return CatalogoExames.query.filter(
            CatalogoExames.nome_exame.ilike(f"%{termo}%"), CatalogoExames.ativo.is_(True)
        ).limit(20).all()

    def save(self, entity: CatalogoExames) -> CatalogoExames:
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

    def find_all(self) -> List[CatalogoExames]:
        return CatalogoExames.query.all()



