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
    __table_args__ = ()  # id_catalogo/id_resultado_prescricao já indexados pela FK

    id = db.Column("id_prescricao", BigIntPK, primary_key=True, autoincrement=True)
    id_resultado_prescricao = db.Column(db.BigInteger, db.ForeignKey("resultado_prescricao.id_resultado"))
    id_catalogo = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    duracao = db.Column(db.String(100))
    orientacoes = db.Column(db.Text)
    uuid = db.Column("uuid_prescricao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_output_origem = db.Column(db.BigInteger, db.ForeignKey("output_bion.id_output"))
    origem_sugestao = db.Column(db.Enum("medico", "bion_ia", "protocolo"),
                                 nullable=False, default="medico")
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    resultado_prescricao = db.relationship("ResultadoPrescricao", back_populates="prescricoes")
    catalogo_medicamentos = db.relationship("CatalogoMedicamentos", back_populates="prescricoes")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "origem_sugestao": self.origem_sugestao,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "duracao": self.duracao,
            "orientacoes": self.orientacoes,
            "medicamento": self.catalogo_medicamentos.to_dict() if self.catalogo_medicamentos else None,
        }

    def __repr__(self):
        return f"<Prescricao {self.id}>"