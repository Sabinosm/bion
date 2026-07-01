from typing import Optional, List

from src.database import db
from src.core.interfaces import IRepository
from src.database.usuarios import Configuracao


class ConfiguracaoRepository(IRepository[Configuracao]):

    def find_by_id(self, id: int) -> Optional[Configuracao]:
        return db.session.get(Configuracao, id)

    def find_by_uuid(self, uuid: str) -> Optional[Configuracao]:
        return Configuracao.query.filter_by(uuid=uuid).first()

    def find_by_usuario(self, id_usuario: int) -> Optional[Configuracao]:
        return Configuracao.query.filter_by(id_usuario=id_usuario).first()

    def save(self, entity: Configuracao) -> Configuracao:
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

    def find_all(self) -> List[Configuracao]:
        return Configuracao.query.all()
