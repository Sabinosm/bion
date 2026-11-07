from datetime import datetime, timezone
import uuid as _uuid
import decimal

from src.models import db
from src.models.types import BigIntPK


class OutputBion(db.Model):
    __tablename__ = "output_bion"

    __table_args__ = (
        db.Index("ix_output_bion_atendimento_criado", "id_atendimento", "criado_em"),
        db.Index("ix_output_bion_atendimento_status", "id_atendimento", "status"),
    )

    id = db.Column("id_output", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_output",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_atendimento = db.Column(
        db.BigInteger, db.ForeignKey("atendimento.id_atendimento"), nullable=False
    )
    input_ia_json = db.Column(db.JSON)
    versao_input_model = db.Column(db.SmallInteger)
    requisicoes_ia_json = db.Column(db.JSON)
    output_ia_json = db.Column(db.JSON)
    versao_modelo_ia = db.Column(db.String(50))
    indice_completude = db.Column(db.Numeric(5, 2))
    indice_confianca = db.Column(db.Numeric(5, 2))
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    status = db.Column(
        db.Enum("processando", "concluido", "falhou"), nullable=False, default="processando"
    )
    erro_codigo = db.Column(db.String(40))
    concluido_em = db.Column(db.DateTime(timezone=True))

    atendimento = db.relationship("Atendimento", back_populates="outputs_bion")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="output_bion")
    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="output_origem")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "versao_input_model": self.versao_input_model,
            "output_ia": self.output_ia_json,
            "versao_modelo_ia": self.versao_modelo_ia,
            "indice_completude": (
                float(self.indice_completude) if self.indice_completude is not None else None
            ),
            "indice_confianca": (
                float(self.indice_confianca) if self.indice_confianca is not None else None
            ),
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "status": self.status,
            "erro_codigo": self.erro_codigo,
            "concluido_em": self.concluido_em.isoformat() if self.concluido_em else None,
        }

    def __repr__(self):
        return f"<OutputBion {self.uuid}>"
