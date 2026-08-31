"""
ObservacaoTipoSanguineo — espelha Observation (LOINC 882-1) do FHIR.

Extraído da coluna tipo_sanguineo de Paciente: tipo sanguíneo é
resultado de exame clínico, com data de registro e quem coletou --
informação que a coluna solta não guardava.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class ObservacaoTipoSanguineo(db.Model):
    __tablename__ = "observacao_tipo_sanguineo"

    id = db.Column("id_observacao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_observacao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    tipo_sanguineo = db.Column(
        db.Enum("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "desconhecido"),
        nullable=False)
    registrado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    data_registro = db.Column(db.DateTime(timezone=True),
                               default=lambda: datetime.now(timezone.utc), nullable=False)
    codigo_loinc = db.Column(db.String(20), default="882-1")

    paciente = db.relationship("Paciente", back_populates="observacoes_tipo_sanguineo")
    # NOVO: contrapartida para expor quem registrou no to_dict() --
    # mesmo padrão usado em Paciente.usuario_cadastro.
    usuario_registro = db.relationship("Usuario", foreign_keys=[registrado_por])

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_sanguineo": self.tipo_sanguineo,
            "data_registro": self.data_registro.isoformat() if self.data_registro else None,
            # NOVO: nome de quem registrou -- Usuario.nome_completo não
            # é cifrado (confirmado na sessão anterior), então pode ir
            # direto sem passar por aes_decrypt.
            "registrado_por": self.usuario_registro.nome_completo if self.usuario_registro else None,
        }

    def __repr__(self):
        return f"<ObservacaoTipoSanguineo {self.uuid} [{self.tipo_sanguineo}]>"