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


class DoencaCronica(db.Model):
    __tablename__ = "doenca_cronica"

    id = db.Column("id_doenca_cronica", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_doenca_cronica", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    codigo_cid10 = db.Column(db.String(10), nullable=False)
    descricao_cid10 = db.Column(db.String(255), nullable=False)
    desde = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum("ativa", "em-remissao"), nullable=False)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="doencas")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_cid10": self.codigo_cid10,
            "descricao_cid10": self.descricao_cid10,
            "desde": self.desde.isoformat() if self.desde else None,
            "status": self.status,
            "observacoes": self.observacoes,
        }

    def __repr__(self):
        return f"<DoencaCronica {self.uuid} [{self.codigo_cid10}]>"
