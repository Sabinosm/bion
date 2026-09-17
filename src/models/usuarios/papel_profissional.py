"""
PapelProfissional — espelha o PractitionerRole do FHIR.

Guarda o registro profissional (conselho, UF, especialidade/RQE) de um
usuario. A autorizacao de rota le esse papel no login (via
Usuario.papel_ativo) e o resultado fica cacheado na sessao.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class PapelProfissional(db.Model):
    __tablename__ = "papel_profissional"

    __table_args__ = (
        db.Index('ix_papel_usuario_tipo_ativo',
                  'id_usuario', 'tipo_papel', 'ativo'),
    )

    id = db.Column("id_papel_profissional", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_papel_profissional", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)

    tipo_papel = db.Column(db.Enum("medico", "enfermeiro"), nullable=False)
    numero_conselho = db.Column(db.String(20), nullable=False)
    uf_conselho = db.Column(db.String(2), nullable=False)
    especialidade = db.Column(db.String(100), nullable=True)  # so enfermeiro usa hoje
    rqe = db.Column(db.String(20), nullable=True)              # so medico usa hoje

    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario", back_populates="papeis")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_papel": self.tipo_papel,
            "numero_conselho": self.numero_conselho,
            "uf_conselho": self.uf_conselho,
            "especialidade": self.especialidade,
            "rqe": self.rqe,
            "ativo": self.ativo,
        }