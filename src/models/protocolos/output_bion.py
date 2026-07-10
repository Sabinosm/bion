"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

ProtocoloCatalogo era um stub (so id/uuid/criado_em), mas o
ProtocoloFactory (app/protocolo/factory.py) ja acessava `catalogo.sigla`
para escolher o motor certo (MTS/NEWS2/PP) -- isso quebraria em runtime
assim que a factory fosse chamada. Completado aqui com sigla e os demais
campos do schema.

OutputBion tambem era stub, mas ia/controller.py ja acessava
`output.output_ia_json` -- tambem completado.
"""

from datetime import datetime, timezone
import uuid as _uuid
import decimal

from src.models import db
from src.models.types import BigIntPK


class OutputBion(db.Model):
    __tablename__ = "output_bion"

    id = db.Column("id_output", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_output", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_input = db.Column(db.BigInteger, db.ForeignKey("input_protocolo.id_input"))
    output_ia_json = db.Column(db.JSON)
    versao_modelo_ia = db.Column(db.String(50))
    indice_completude = db.Column(db.Numeric(5, 2))
    indice_confianca = db.Column(db.Numeric(5, 2))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    input_protocolo = db.relationship("InputProtocolo", back_populates="outputs")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="output_bion")
    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="output_origem")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "output_ia": self.output_ia_json,
            "versao_modelo_ia": self.versao_modelo_ia,
            "indice_completude": float(self.indice_completude) if self.indice_completude is not None else None,
            "indice_confianca": float(self.indice_confianca) if self.indice_confianca is not None else None,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    def __repr__(self):
        return f"<OutputBion {self.uuid}>"
