"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Novo: configuracao parametrizavel de um protocolo de escore (parametros,
regras de override e faixas de interpretacao guardados como JSON, com
checksum e versionamento de schema). Relacao 1:1 com ProtocoloCatalogo
(UNIQUE em id_protocolo_catalogo).
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class ProtocoloEscoreConfig(db.Model):
    __tablename__ = "protocolo_escore_config"

    id = db.Column("id_escore_config", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_escore_config", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_protocolo_catalogo = db.Column(db.BigInteger,
                                       db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"),
                                       unique=True, nullable=False)
    parametros_json = db.Column(db.JSON, nullable=True)
    regra_override_json = db.Column(db.JSON, nullable=True)
    faixas_interpretacao_json = db.Column(db.JSON, nullable=True)
    schema_version = db.Column(db.String(20), nullable=False, default="1.0")
    checksum = db.Column(db.String(64), nullable=True)
    publicado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=True)
    status = db.Column(db.Enum("ativo", "descontinuado"), nullable=False, default="ativo")
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="escore_config")
    publicador = db.relationship("Usuarios", foreign_keys=[publicado_por])

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "parametros": self.parametros_json,
            "regra_override": self.regra_override_json,
            "faixas_interpretacao": self.faixas_interpretacao_json,
            "schema_version": self.schema_version,
            "checksum": self.checksum,
            "status": self.status,
        }

    def __repr__(self):
        return f"<ProtocoloEscoreConfig {self.uuid} protocolo={self.id_protocolo_catalogo}>"