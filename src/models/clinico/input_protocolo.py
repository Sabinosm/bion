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


class InputProtocolo(db.Model):
    __tablename__ = "input_protocolo"

    id = db.Column("id_input", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_input", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_coleta_clinica = db.Column(db.BigInteger, db.ForeignKey("coleta_clinica.id_coleta"))
    tipo_input = db.Column(db.Enum("triagem", "consulta"))
    input_json = db.Column(db.JSON)
    queixa_principal = db.Column(db.Text)
    valor_avpu = db.Column(db.String(20))
    dados_criticos_ausentes_json = db.Column(db.JSON)

    coleta_clinica = db.relationship("ColetaClinica", back_populates="inputs_protocolo")
    outputs = db.relationship("OutputBion", back_populates="input_protocolo")
    execucoes = db.relationship("InputProtocoloExecucao", back_populates="input_protocolo",
                                 cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_input": self.tipo_input,
            "input": self.input_json,
            "queixa_principal": self.queixa_principal,
            "valor_avpu": self.valor_avpu,
        }

    def __repr__(self):
        return f"<InputProtocolo {self.uuid}>"
