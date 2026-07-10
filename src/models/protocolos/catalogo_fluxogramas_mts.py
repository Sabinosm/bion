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


class CatalogoFluxogramasMts(db.Model):
    __tablename__ = "catalogo_fluxogramas_mts"

    id = db.Column("id_fluxo_mts",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_fluxo_mts", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    codigo_fluxograma = db.Column(db.String(50), nullable=False)
    nome_fluxograma = db.Column(db.String(255), nullable=False)
    status = db.Column(db.Enum("ativo", "descontinuado"), nullable=False, default="ativo")
    estrutura_json = db.Column(db.JSON)

    protocolos_mts = db.relationship("ProtocoloMts", back_populates="fluxo_mts")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_fluxograma": self.codigo_fluxograma,
            "nome_fluxograma": self.nome_fluxograma,
            "status": self.status,
        }

    def __repr__(self):
        return f"<CatalogoFluxogramasMts {self.uuid} [{self.codigo_fluxograma}]>"
