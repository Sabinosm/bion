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


class InputProtocoloExecucao(db.Model):
    __tablename__ = "input_protocolo_execucao"

    id = db.Column("id_input_execucao",BigIntPK, primary_key=True, autoincrement=True)
    id_input = db.Column(db.BigInteger, db.ForeignKey("input_protocolo.id_input"))
    id_protocolo_catalogo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"))

    input_protocolo = db.relationship("InputProtocolo", back_populates="execucoes")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="execucoes")

    def __repr__(self):
        return f"<InputProtocoloExecucao {self.id}>"
