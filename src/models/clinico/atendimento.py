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


class Atendimento(db.Model):
    __tablename__ = "atendimento"

    id = db.Column("id_atendimento",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_atendimento",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_consulta = db.Column(db.BigInteger, db.ForeignKey("consulta.id_consulta"), nullable=False)
    tipo_atendimento = db.Column(
        db.Enum("triagem", "avaliacao-medica", "reavaliacao", "alta", "procedimento"),
        nullable=False)
    realizado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    status = db.Column(db.Enum("em-andamento", "finalizado", "cancelado"),
                        nullable=False, default="em-andamento")
    data_hora_inicio = db.Column(db.DateTime(timezone=True), nullable=False,
                                  default=lambda: datetime.now(timezone.utc))
    data_hora_fim = db.Column(db.DateTime(timezone=True))
    habitos_atendimento_json = db.Column(db.JSON)
    observacoes_profissional = db.Column(db.Text)

    consulta = db.relationship("Consulta", back_populates="atendimentos")
    usuario = db.relationship("Usuario")
    coletas_clinicas = db.relationship("ColetaClinica", back_populates="atendimento",
                                        cascade="all, delete-orphan")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="atendimento",
                                             cascade="all, delete-orphan")
    sinais_vitais = db.relationship("SinalVital", back_populates="atendimento",
                                     cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_atendimento": self.tipo_atendimento,
            "status": self.status,
            "data_hora_inicio": self.data_hora_inicio.isoformat() if self.data_hora_inicio else None,
            "data_hora_fim": self.data_hora_fim.isoformat() if self.data_hora_fim else None,
            "observacoes_profissional": self.observacoes_profissional,
            "consulta_uuid": self.consulta.uuid if self.consulta else None,
        }

    def __repr__(self):
        return f"<Atendimento {self.uuid} [{self.tipo_atendimento}]>"
