from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import Consentimento

class ConsentimentoRepository(IRepository[Consentimento]):

    def find_by_id(self, id: int) -> Optional[Consentimento]:
        return db.session.get(Consentimento, id)

    def find_by_uuid(self, uuid: str) -> Optional[Consentimento]:
        return Consentimento.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Consentimento]:
        return Consentimento.query.filter_by(id_paciente=id_paciente).all()

    def find_ativo_por_paciente(self, id_paciente: int) -> Optional[Consentimento]:
        return Consentimento.query.filter_by(id_paciente=id_paciente, status="ativo").first()

    def save(self, entity: Consentimento, commit: bool = True) -> Consentimento:
        db.session.add(entity)
        if commit:
            db.session.commit()
        else:
            db.session.flush()  # flush sem commit, pra manter atomicidade do log
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True