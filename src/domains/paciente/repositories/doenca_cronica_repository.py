from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func

class DoencaCronicaRepository(IRepository[DoencaCronica]):

    def find_by_id(self, id: int) -> Optional[DoencaCronica]:
        return db.session.get(DoencaCronica, id)

    def find_by_uuid(self, uuid: str) -> Optional[DoencaCronica]:
        return DoencaCronica.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[DoencaCronica]:
        return DoencaCronica.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: DoencaCronica) -> DoencaCronica:
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
    
# --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10) -> list:
        """Ranking de codigo_cid10 com status='ativa', entre os pacientes
        da empresa. Não filtra por período -- é o estado atual da base,
        não um evento pontual.
 
        Retorna: [{"codigo_cid10": "I10", "descricao_cid10": "Hipertensão", "total": 214}, ...]
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.pacientes import Paciente
 
        linhas = (
            db.session.query(
                DoencaCronica.codigo_cid10.label("codigo"),
                DoencaCronica.descricao_cid10.label("descricao"),
                func.count(DoencaCronica.id).label("total"),
            )
            .join(Paciente, DoencaCronica.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(DoencaCronica.status == "ativa")
            .group_by(DoencaCronica.codigo_cid10, DoencaCronica.descricao_cid10)
            .order_by(func.count(DoencaCronica.id).desc())
            .limit(limite)
            .all()
        )
        return [
            {"codigo_cid10": linha.codigo, "descricao_cid10": linha.descricao, "total": linha.total}
            for linha in linhas
        ]