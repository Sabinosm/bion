from datetime import datetime, timezone
from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import ReacaoAlergia


class ReacaoAlergiaRepository(IRepository[ReacaoAlergia]):
    """Reações de uma alergia. Nada é apagado: leituras 'normais' filtram
    deletado == False; remoção é soft_delete."""

    def find_by_id(self, id: int) -> Optional[ReacaoAlergia]:
        return (ReacaoAlergia.query
                .filter(ReacaoAlergia.id == id, ReacaoAlergia.deletado == False).first())

    def find_by_uuid(self, uuid: str) -> Optional[ReacaoAlergia]:
        return (ReacaoAlergia.query
                .filter(ReacaoAlergia.uuid == uuid, ReacaoAlergia.deletado == False).first())

    def find_por_alergia(self, id_alergia: int) -> List[ReacaoAlergia]:
        return (ReacaoAlergia.query
                .filter(ReacaoAlergia.id_alergia == id_alergia, ReacaoAlergia.deletado == False)
                .order_by(ReacaoAlergia.criado_em, ReacaoAlergia.id).all())

    def save(self, entity: ReacaoAlergia, commit: bool = True) -> ReacaoAlergia:
        db.session.add(entity)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError("Reação não é apagada fisicamente; use soft_delete.")

    def delete_by_uuid(self, uuid: str) -> bool:
        raise NotImplementedError("Reação não é apagada fisicamente; use soft_delete.")

    def soft_delete(self, entity: ReacaoAlergia, motivo: str,
                    observacoes_delete: Optional[str] = None,
                    deletado_por: Optional[int] = None,
                    id_atendimento_delecao: Optional[int] = None,
                    commit: bool = True) -> ReacaoAlergia:
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        entity.deletado_por = deletado_por
        entity.id_atendimento_delecao = id_atendimento_delecao
        return self.save(entity, commit=commit)