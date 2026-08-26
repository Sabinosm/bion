"""Repositório de acesso a dados da entidade PrescricaoExame."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import PrescricaoExame


class PrescricaoExameRepository(IRepository[PrescricaoExame]):

    def find_by_id(self, id: int) -> Optional[PrescricaoExame]:
        return db.session.get(PrescricaoExame, id)

    def find_by_uuid(self, uuid: str) -> Optional[PrescricaoExame]:
        return PrescricaoExame.query.filter_by(uuid=uuid).first()

    def save(self, entity: PrescricaoExame) -> PrescricaoExame:
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

    def find_all(self) -> List[PrescricaoExame]:
        return PrescricaoExame.query.all()

    # --- D3: Urgência de exames -- IA vs. profissional ---
    def urgencia_por_origem(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Contagem de PrescricaoExame cruzando urgencia x origem_sugestao,
        filtrado por empresa (via ResultadoPrescricao -> Atendimento ->
        realizado_por -> Usuario) e por janela de tempo.

        Retorna lista de dicts:
        [{"urgencia": "urgente", "origem_sugestao": "bion_ia", "total": 26}, ...]
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import ResultadoPrescricao, Atendimento

        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                PrescricaoExame.urgencia.label("urgencia"),
                PrescricaoExame.origem_sugestao.label("origem_sugestao"),
                func.count(PrescricaoExame.id).label("total"),
            )
            .join(ResultadoPrescricao, PrescricaoExame.id_resultado == ResultadoPrescricao.id)
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(PrescricaoExame.criado_em >= limite)
            .group_by(PrescricaoExame.urgencia, PrescricaoExame.origem_sugestao)
            .all()
        )
        return [
            {"urgencia": linha.urgencia, "origem_sugestao": linha.origem_sugestao, "total": linha.total}
            for linha in linhas
        ]