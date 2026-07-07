from typing import Optional, List

from src.database import db
from src.core.interfaces import IRepository
from src.database.corp import Empresa


class EmpresaRepository(IRepository[Empresa]):

    def find_by_id(self, id: int) -> Optional[Empresa]:
        return db.session.get(Empresa, id)

    def find_by_uuid(self, uuid: str) -> Optional[Empresa]:
        return Empresa.query.filter_by(uuid=uuid).first()

    def find_by_cnpj(self, cnpj: str) -> Optional[Empresa]:
        return Empresa.query.filter_by(cnpj=cnpj).first()

    def save(self, entity: Empresa, commit: bool = True) -> Empresa:
        if commit == True:
            db.session.add(entity)
            db.session.commit()
        else:
            """
            Usado quando quem está chamando quer controlar a transação
            por fora (ex: criar empresa + admin juntos). Só adiciona/dá
            flush — quem chamou decide quando commitar ou dar rollback.
            """
            # já gera o entity.id, mas não fecha a transação
            db.session.add(entity)
            db.session.flush()
            
        return entity

        
    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[Empresa]:
        return Empresa.query.all()
