"""atendimento.py -- model do Atendimento.

Etapa de uma Consulta (triagem, avaliação médica, reavaliação etc.), sempre feita por um
único profissional. Guarda status, horários, observações, a conferência do binário e o
motivo de cancelamento. A posse por empresa vem da Consulta. O to_dict() usa só dados já
carregados pelas relações, sem consultar services.
"""

from datetime import datetime, timezone
import uuid as _uuid
from src.models import db
from src.models.types import BigIntPK

class Atendimento(db.Model):
    __tablename__ = "atendimento"

    __table_args__ = (
        db.Index('ix_atendimento_realizado_por_status_data',
                  'realizado_por', 'status', 'data_hora_inicio'),
        # cobre A1/A3 (status + data) e A2 (join + data), com realizado_por
        # como primeira coluna já que ele entra em toda query
    )
    
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
    # Conferência do binário: {"v":1,"<secao>":{"estado":"preenchido|nega|nao-coletado"}}.
    # Lida/escrita SÓ pelo objeto Binario (binario_model.py). Chave ausente = pendente.
    binario = db.Column(db.JSON, nullable=True)
    # Motivo (opcional) do cancelamento; só preenchido por cancelar().
    motivo_cancelamento = db.Column(
        db.Enum("erro-abertura", "paciente-nao-compareceu", "paciente-recusou",
                "transferencia", "outro"),
        nullable=True)

    consulta = db.relationship("Consulta", back_populates="atendimentos")
    usuario = db.relationship("Usuario")
    coletas_clinicas = db.relationship("ColetaClinica", back_populates="atendimento",
                                        cascade="all, delete-orphan")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="atendimento",
                                             cascade="all, delete-orphan")
    sinais_vitais = db.relationship("SinalVital", back_populates="atendimento",
                                     cascade="all, delete-orphan")
    outputs_bion = db.relationship("OutputBion", back_populates="atendimento")
    condutas_enfermagem = db.relationship("CondutaEnfermagem", back_populates="atendimento",
                                       cascade="save-update, merge",
                                       passive_deletes="all")

   
    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_atendimento": self.tipo_atendimento,
            "status": self.status,
            "data_hora_inicio": self.data_hora_inicio.isoformat() if self.data_hora_inicio else None,
            "data_hora_fim": self.data_hora_fim.isoformat() if self.data_hora_fim else None,
            "observacoes_profissional": self.observacoes_profissional,
            "motivo_cancelamento": self.motivo_cancelamento,
            "consulta_uuid": self.consulta.uuid if self.consulta else None,
            "realizado_por": self.usuario.uuid if self.usuario else None,
        }

    def __repr__(self):
        return f"<Atendimento {self.uuid} [{self.tipo_atendimento}]>"