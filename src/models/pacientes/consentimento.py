"""
Dominio Paciente.

Paciente e PacientePessoal ja estavam quase completos no projeto original.
Alergia, DoencaCronica e MedicamentoEmUso nao existiam como classes
proprias (so eram citadas em relationship() sem definicao) -- criadas
aqui. Consentimento era stub; completado.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Consentimento(db.Model):
    __tablename__ = "consentimento_lgpd"

    id = db.Column("id_consentimento", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_consentimento", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    coletado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    versao_termo = db.Column(db.String(50), nullable=False)
    data_consentimento = db.Column(db.DateTime(timezone=True), nullable=False)
    canal_coleta = db.Column(
        db.Enum("presencial-papel", "presencial-digital", "portal-online", "totem"),
        nullable=False)
    status = db.Column(db.Enum("ativo", "revogado", "expirado"),
                        nullable=False, default="ativo")
    escopo_consentimento_json = db.Column(db.JSON)
    data_revogacao = db.Column(db.DateTime(timezone=True))
    motivo_revogacao = db.Column(db.Text)
    hash_documento = db.Column(db.String(64))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="consentimentos")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "versao_termo": self.versao_termo,
            "data_consentimento": self.data_consentimento.isoformat()
            if self.data_consentimento else None,
            "canal_coleta": self.canal_coleta,
            "status": self.status,
            "data_revogacao": self.data_revogacao.isoformat() if self.data_revogacao else None,
        }

    def __repr__(self):
        return f"<Consentimento {self.uuid} [{self.status}]>"
