from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Configuracao(db.Model):
    __tablename__ = "configuracao"

    id = db.Column("id_configuracao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_configuracao",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), unique=True, nullable=False
    )
    configuracoes_json = db.Column(db.JSON)
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    usuario = db.relationship("Usuario", back_populates="configuracao")
    protocolos = db.relationship(
        "ConfiguracaoProtocolo", back_populates="configuracao", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "design": (self.configuracoes_json or {}).get("design", {}),
            "preferencias": (self.configuracoes_json or {}).get("preferencias", {}),
            "protocolos": {
                (p.protocolo.sigla if p.protocolo else p.id_protocolo): {
                    "nome": p.protocolo.nome_protocolo if p.protocolo else None,
                    "tipo": p.protocolo.tipo_protocolo if p.protocolo else None,
                    "id": p.id_protocolo,
                    "uuid": p.protocolo.uuid if p.protocolo else None,
                    "em_uso": p.em_uso,
                    "escopo_default": p.escopo_default,
                }
                for p in self.protocolos
            },
        }

    def __repr__(self):
        return f"<Configuracao {self.uuid}>"
