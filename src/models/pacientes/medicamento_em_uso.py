"""
Dominio Paciente.

Paciente e PacientePessoal ja estavam quase completos no projeto original.
Alergia, DoencaCronica e MedicamentoEmUso nao existiam como classes
proprias (so eram citadas em relationship() sem definicao) -- criadas
aqui. Consentimento era stub; completado.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class MedicamentoEmUso(db.Model):
    __tablename__ = "medicamentos_em_uso"

    id = db.Column("id_medicamento_uso", BigIntPK, primary_key=True, autoincrement=True)
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    id_catalogo = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"), nullable=False)
    descricao = db.Column(db.Text)
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    desde = db.Column(db.Date)
    flag_em_uso = db.Column(db.Boolean, default=True)

    paciente = db.relationship("Paciente", back_populates="medicamentos_em_uso")
    catalogo_medicamentos = db.relationship("CatalogoMedicamentos",
                                            back_populates="medicamentos_em_uso")

    def to_dict(self):
        return {
            "id": self.id,
            "descricao": self.descricao,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "desde": self.desde.isoformat() if self.desde else None,
            "flag_em_uso": self.flag_em_uso,
        }

    def __repr__(self):
        return f"<MedicamentoEmUso {self.id}>"
