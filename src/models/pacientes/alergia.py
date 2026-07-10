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


class Alergia(db.Model):
    __tablename__ = "alergia"

    id = db.Column("id_alergia", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_alergia", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    substancia = db.Column(db.String(255), nullable=False)
    codigo_substancia = db.Column(db.String(100))
    tipo_reacao = db.Column(
        db.Enum("cutanea", "respiratoria", "anafilaxia", "gastrointestinal",
                "cardiovascular", "sistemica"),
        nullable=False)
    gravidade = db.Column(db.Enum("leve", "moderada", "grave", "anafilaxia"),
                           nullable=False)
    descricao_reacao = db.Column(db.Text)
    flag_confirmado = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="alergias")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "substancia": self.substancia,
            "tipo_reacao": self.tipo_reacao,
            "gravidade": self.gravidade,
            "descricao_reacao": self.descricao_reacao,
            "flag_confirmado": self.flag_confirmado,
        }

    def __repr__(self):
        return f"<Alergia {self.uuid} [{self.substancia}]>"
