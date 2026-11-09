"""reacao_alergia_repository.py

Acesso a dados de ReacaoAlergia, o histórico de ocorrências de uma alergia. Nada
é apagado: as leituras "normais" filtram deletado == False e a remoção é soft
delete, com motivo, autor e atendimento da remoção. commit=True confirma;
commit=False só faz flush, para compor operações atômicas.
"""
from datetime import datetime, timezone
from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import ReacaoAlergia


class ReacaoAlergiaRepository(IRepository[ReacaoAlergia]):

    def find_by_id(self, id: int) -> Optional[ReacaoAlergia]:
        return ReacaoAlergia.query.filter(ReacaoAlergia.id == id, ReacaoAlergia.deletado.is_(False)).first()

    def find_by_uuid(self, uuid: str) -> Optional[ReacaoAlergia]:
        return ReacaoAlergia.query.filter(ReacaoAlergia.uuid == uuid, ReacaoAlergia.deletado.is_(False)).first()

    def find_por_alergia(self, id_alergia: int) -> List[ReacaoAlergia]:
        return (
            ReacaoAlergia.query
            .filter(ReacaoAlergia.id_alergia == id_alergia, ReacaoAlergia.deletado.is_(False))
            .order_by(ReacaoAlergia.criado_em, ReacaoAlergia.id)
            .all()
        )

    def confirmar(self, commit: bool = True) -> None:
        """commit=True: commita; commit=False: só flush (a transação segue aberta)."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    def save(self, entity: ReacaoAlergia, commit: bool = True) -> ReacaoAlergia:
        db.session.add(entity)
        self.confirmar(commit)
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
        """Marca a reação como removida (e quem/qual atendimento) sem apagar a linha."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        entity.deletado_por = deletado_por
        entity.id_atendimento_delecao = id_atendimento_delecao
        return self.save(entity, commit=commit)
