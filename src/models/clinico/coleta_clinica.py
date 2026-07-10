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


class ColetaClinica(db.Model):
    __tablename__ = "coleta_clinica"

    id = db.Column("id_coleta",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_coleta",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"), nullable=False)
    desde_quando_sintomas = db.Column(db.SmallInteger)  # horas

    atendimento = db.relationship("Atendimento", back_populates="coletas_clinicas")
    inputs_protocolo = db.relationship("InputProtocolo", back_populates="coleta_clinica",
                                        cascade="all, delete-orphan")

    def to_dict(self):
        return {"uuid": self.uuid, "desde_quando_sintomas": self.desde_quando_sintomas}

    def __repr__(self):
        return f"<ColetaClinica {self.uuid}>"
