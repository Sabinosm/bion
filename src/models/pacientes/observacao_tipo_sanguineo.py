from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class ObservacaoTipoSanguineo(db.Model):
    __tablename__ = "observacao_tipo_sanguineo"
    __table_args__ = (db.Index("idx_obs_tsang_paciente_data", "id_paciente", "data_registro"),)

    id = db.Column("id_observacao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_observacao",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    tipo_sanguineo = db.Column(
        db.Enum("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "desconhecido"), nullable=False
    )
    registrado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    data_registro = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    codigo_loinc = db.Column(db.String(20), default="882-1")
    id_atendimento_origem = db.Column(
        db.BigInteger,
        db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT"),
        nullable=True,
    )

    paciente = db.relationship("Paciente", back_populates="observacoes_tipo_sanguineo")
    usuario_registro = db.relationship("Usuario", foreign_keys=[registrado_por])
    atendimento_origem = db.relationship("Atendimento", foreign_keys=[id_atendimento_origem])

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_sanguineo": self.tipo_sanguineo,
            "data_registro": self.data_registro.isoformat() if self.data_registro else None,
            "registrado_por": (
                self.usuario_registro.nome_completo if self.usuario_registro else None
            ),
            "atendimento_origem_uuid": (
                self.atendimento_origem.uuid if self.atendimento_origem else None
            ),
        }

    def __repr__(self):
        return f"<ObservacaoTipoSanguineo {self.uuid} [{self.tipo_sanguineo}]>"
