from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func

class MedicamentoEmUsoRepository(IRepository[MedicamentoEmUso]):

    def find_by_id(self, id: int) -> Optional[MedicamentoEmUso]:
        return db.session.get(MedicamentoEmUso, id)

    def find_by_uuid(self, uuid: str) -> Optional[MedicamentoEmUso]:
        # ALTERADO: agora existe uuid de verdade (era None antes, por
        # falta da coluna -- ver 08_medicamentos_em_uso_migration.sql)
        return MedicamentoEmUso.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[MedicamentoEmUso]:
        return MedicamentoEmUso.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: MedicamentoEmUso) -> MedicamentoEmUso:
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