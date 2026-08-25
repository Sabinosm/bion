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
    
     # --- F2: Pacientes em uso contínuo de medicação (%) ---
    def percentual_pacientes_em_uso_continuo(self, id_empresa: int) -> dict:
        """% de pacientes (distintos) da empresa com status_uso='ativo'
        em pelo menos 1 medicamento, sobre o total de pacientes cadastrados.
 
        Retorna: {"total_pacientes": int, "em_uso_continuo": int, "percentual": float}
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.pacientes import Paciente
 
        total_pacientes = (
            db.session.query(func.count(Paciente.id))
            .join(Usuario, Paciente.cadastrado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .scalar() or 0
        )
 
        em_uso = (
            db.session.query(func.count(func.distinct(MedicamentoEmUso.id_paciente)))
            .join(Paciente, MedicamentoEmUso.id_paciente == Paciente.id)
            .join(Usuario, Paciente.cadastrado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(MedicamentoEmUso.status_uso == "ativo")
            .scalar() or 0
        )
 
        percentual = round((em_uso / total_pacientes) * 100, 1) if total_pacientes else 0.0
 
        return {"total_pacientes": total_pacientes, "em_uso_continuo": em_uso, "percentual": percentual}