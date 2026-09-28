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


class ProtocoloPersonalizado(db.Model):
    __tablename__ = "protocolo_personalizado"

    id = db.Column("id_protocolo_personalizado", BigIntPK, primary_key=True, autoincrement=True)
    id_modulo = db.Column(db.BigInteger, db.ForeignKey("catalogo_modulos.id_modulo"))
    id_protocolo_catalogo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"))
    codigo_protocolo = db.Column(db.String(100))

    modulo = db.relationship("CatalogoModulos", back_populates="protocolos_personalizados")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo",
                                          back_populates="protocolos_personalizados")

    def __repr__(self):
        return f"<ProtocoloPersonalizado {self.id}>"
