"""
Dominio Clinico (nucleo do ciclo de vida do atendimento/visita).

Consulta, Atendimento e SinalVital ja estavam completos no projeto
original. ColetaClinica, ResultadoPrescricao, InputProtocolo,
InputProtocoloExecucao, Prescricao e PrescricaoExame eram stubs ou nem
existiam como classe -- completados aqui com os campos do schema.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Prescricao(db.Model):
    __tablename__ = "prescricao"

    id = db.Column("id_prescricao", BigIntPK, primary_key=True, autoincrement=True)
    id_resultado_prescricao = db.Column(db.BigInteger, db.ForeignKey("resultado_prescricao.id_resultado"))
    id_catalogo = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    duracao = db.Column(db.String(100))
    orientacoes = db.Column(db.Text)

    resultado_prescricao = db.relationship("ResultadoPrescricao", back_populates="prescricoes")
    catalogo_medicamentos = db.relationship("CatalogoMedicamentos", back_populates="prescricoes")

    def to_dict(self):
        return {
            "id": self.id,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "duracao": self.duracao,
            "orientacoes": self.orientacoes,
            "medicamento": self.catalogo_medicamento.to_dict() if self.catalogo_medicamento else None,
        }

    def __repr__(self):
        return f"<Prescricao {self.id}>"
