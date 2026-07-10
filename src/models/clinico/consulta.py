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


class Consulta(db.Model):
    __tablename__ = "consulta"

    id = db.Column("id_consulta",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_consulta",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column("id_paciente",db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    tipo_consulta = db.Column(db.Enum("triagem", "consulta-medica"), nullable=False)
    origem_encaminhamento = db.Column(
        db.Enum("espontanea", "SAMU", "transferencia", "regulacao"),
        nullable=False, default="espontanea")
    status_consulta = db.Column(
        db.Enum("aguardando-triagem", "em-triagem", "aguardando-medico",
                "em-atendimento", "em-observacao", "encerrada"),
        nullable=False, default="aguardando-triagem")
    data_hora_inicio = db.Column(db.DateTime(timezone=True), nullable=False,
                                  default=lambda: datetime.now(timezone.utc))
    data_hora_fim = db.Column(db.DateTime(timezone=True))
    desfecho_final = db.Column(
        db.Enum("alta", "internacao", "transferencia", "obito", "evasao"))
    iniciada_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    finalizada_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="consultas")
    usuario_iniciou = db.relationship("Usuario", foreign_keys=[iniciada_por])
    usuario_finalizou = db.relationship("Usuario", foreign_keys=[finalizada_por])
    atendimentos = db.relationship("Atendimento", back_populates="consulta",
                                    cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_consulta": self.tipo_consulta,
            "origem_encaminhamento": self.origem_encaminhamento,
            "status_consulta": self.status_consulta,
            "data_hora_inicio": self.data_hora_inicio.isoformat() if self.data_hora_inicio else None,
            "data_hora_fim": self.data_hora_fim.isoformat() if self.data_hora_fim else None,
            "desfecho_final": self.desfecho_final,
            "paciente_uuid": self.paciente.uuid if self.paciente else None,
        }

    def __repr__(self):
        return f"<Consulta {self.uuid} [{self.status_consulta}]>"
