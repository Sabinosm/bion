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


class ProtocoloMts(db.Model):
    __tablename__ = "protocolo_mts"

    id = db.Column("id_protocolo_mts", BigIntPK, primary_key=True, autoincrement=True)
    id_fluxo_mts = db.Column(db.BigInteger, db.ForeignKey("catalogo_fluxogramas_mts.id_fluxo_mts"))
    id_protocolo_catalogo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"))

    fluxo_mts = db.relationship("CatalogoFluxogramasMts", back_populates="protocolos_mts")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="protocolos_mts")

    def __repr__(self):
        return f"<ProtocoloMts {self.id}>"
