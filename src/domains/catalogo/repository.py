from typing import Optional, List

from src.database import db
from src.core.interfaces import IRepository
from src.database.catalogo import CatalogoExames, CatalogoMedicamentos, InteracoesMedicamentos


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


class CatalogoMedicamentosRepository(IRepository[CatalogoMedicamentos]):

    def find_by_id(self, id: int) -> Optional[CatalogoMedicamentos]:
        return db.session.get(CatalogoMedicamentos, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.filter_by(uuid=uuid).first()

    def buscar_por_principio_ativo(self, termo: str) -> List[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.filter(
            CatalogoMedicamentos.principio_ativo.ilike(f"%{termo}%")
        ).limit(20).all()

    def interacoes_de(self, id_medicamento: int) -> List[InteracoesMedicamentos]:
        return InteracoesMedicamentos.query.filter(
            (InteracoesMedicamentos.id_medicamento_a == id_medicamento) |
            (InteracoesMedicamentos.id_medicamento_b == id_medicamento)
        ).all()

    def save(self, entity: CatalogoMedicamentos) -> CatalogoMedicamentos:
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

    def find_all(self) -> List[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.all()
