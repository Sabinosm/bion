from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK

class InteracoesMedicamentos(db.Model):
    __tablename__ = "interacoes_medicamentos"

    id = db.Column("id_interacao",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_interacao",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_medicamento_a = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    id_medicamento_b = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    gravidade = db.Column(db.String(50))
    mecanismo_efeito = db.Column(db.Text)

    medicamento_a = db.relationship("CatalogoMedicamentos", foreign_keys=[id_medicamento_a],
                                     back_populates="interacoes_como_a")
    medicamento_b = db.relationship("CatalogoMedicamentos", foreign_keys=[id_medicamento_b],
                                     back_populates="interacoes_como_b")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "gravidade": self.gravidade,
            "mecanismo_efeito": self.mecanismo_efeito,
        }

    def __repr__(self):
        return f"<InteracoesMedicamentos {self.uuid}>"
