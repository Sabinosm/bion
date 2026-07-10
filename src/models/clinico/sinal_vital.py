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


class SinalVital(db.Model):
    __tablename__ = "sinal_vital"

    id = db.Column("id_sinal_vital",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_sinal_vital",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"), nullable=False)
    tipo_parametro = db.Column(
        db.Enum("frequencia-respiratoria", "spo2", "pa-sistolica", "pa-diastolica",
                "frequencia-cardiaca", "temperatura", "glicemia-capilar"),
        nullable=False)
    valor_numerico = db.Column(db.Numeric(10, 2), nullable=False)
    unidade = db.Column(
        db.Enum("irpm", "%", "mmHg", "bpm", "°C", "mg-dL"), nullable=False)
    sitio_medicao = db.Column(
        db.Enum("axilar", "oral", "retal", "timpanico", "oximetria-digital",
                "manguito-braco-direito", "manguito-braco-esquerdo"))
    data_hora_medicao = db.Column(db.DateTime(timezone=True), nullable=False,
                                   default=lambda: datetime.now(timezone.utc))
    coletado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    flag_validacao_faixa = db.Column(
        db.Enum("dentro-do-limite", "fora-limite-alertado", "fora-limite-rejeitado"),
        nullable=False, default="dentro-do-limite")
    flag_escala_dpoc = db.Column(db.Boolean, nullable=False, default=False)

    atendimento = db.relationship("Atendimento", back_populates="sinais_vitais")
    usuario = db.relationship("Usuario")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_parametro": self.tipo_parametro,
            "valor_numerico": float(self.valor_numerico) if self.valor_numerico is not None else None,
            "unidade": self.unidade,
            "sitio_medicao": self.sitio_medicao,
            "data_hora_medicao": self.data_hora_medicao.isoformat() if self.data_hora_medicao else None,
            "flag_validacao_faixa": self.flag_validacao_faixa,
        }

    def __repr__(self):
        return f"<SinalVital {self.uuid} [{self.tipo_parametro}={self.valor_numerico}]>"
