from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK

class PrescricaoExame(db.Model):
    __tablename__ = "prescricao_exame"

    id = db.Column("id_prescricao_exame", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_prescricao_exame", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_resultado = db.Column(db.BigInteger, db.ForeignKey("resultado_prescricao.id_resultado"))
    id_exame = db.Column(db.BigInteger, db.ForeignKey("catalogo_exames.id_catalogo_exame"))
    id_output_origem = db.Column(db.BigInteger, db.ForeignKey("output_bion.id_output"))
    urgencia = db.Column(db.Enum("rotina", "urgente", "emergencia"))
    justificativa = db.Column(db.Text)
    origem_sugestao = db.Column(db.Enum("medico", "bion_ia", "protocolo"))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    resultado_prescricao = db.relationship("ResultadoPrescricao", back_populates="prescricoes_exame")
    catalogo_exame = db.relationship("CatalogoExames", back_populates="prescricoes_exame")
    output_origem = db.relationship("OutputBion", back_populates="prescricoes_exame")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "urgencia": self.urgencia,
            "justificativa": self.justificativa,
            "origem_sugestao": self.origem_sugestao,
            "exame": self.catalogo_exame.to_dict() if self.catalogo_exame else None,
        }

    def __repr__(self):
        return f"<PrescricaoExame {self.uuid}>"
