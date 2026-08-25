from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func

class ReacaoAlergiaRepository(IRepository[ReacaoAlergia]):
    """Novo -- suporta o histórico de reações (antes campos soltos em Alergia)."""

    def find_by_id(self, id: int) -> Optional[ReacaoAlergia]:
        return db.session.get(ReacaoAlergia, id)

    def find_by_uuid(self, uuid: str) -> Optional[ReacaoAlergia]:
        return ReacaoAlergia.query.filter_by(uuid=uuid).first()

    def find_por_alergia(self, id_alergia: int) -> List[ReacaoAlergia]:
        return ReacaoAlergia.query.filter_by(id_alergia=id_alergia).all()

    def save(self, entity: ReacaoAlergia) -> ReacaoAlergia:
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

    def delete_by_uuid(self, uuid: str) -> bool:
        """Remove APENAS esta reação específica, preservando a Alergia
        e as demais reações do histórico -- diferente de
        AlergiaRepository.delete_by_uuid(), que apaga tudo."""
        e = self.find_by_uuid(uuid)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True