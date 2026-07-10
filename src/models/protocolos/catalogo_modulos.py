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


class CatalogoModulos(db.Model):
    __tablename__ = "catalogo_modulos"

    id = db.Column("id_modulo",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_modulo", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_modulo = db.Column(db.String(255), nullable=False)
    tipo_modulo = db.Column(
        db.Enum("epidemiologico", "comorbidade", "faixa-etaria", "institucional"),
        nullable=False)
    status = db.Column(db.Enum("ativo", "inativo"), nullable=False, default="ativo")
    descricao = db.Column(db.Text)
    campos_adicionados_json = db.Column(db.JSON)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    protocolos_personalizados = db.relationship("ProtocoloPersonalizado", back_populates="modulo")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_modulo": self.nome_modulo,
            "tipo_modulo": self.tipo_modulo,
            "status": self.status,
            "descricao": self.descricao,
        }

    def __repr__(self):
        return f"<CatalogoModulos {self.uuid} [{self.nome_modulo}]>"
