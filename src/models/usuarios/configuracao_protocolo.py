from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class ConfiguracaoProtocolo(db.Model):
    __tablename__ = "configuracao_protocolo"

    __table_args__ = (
        db.UniqueConstraint("id_configuracao", "id_protocolo", name="uq_config_protocolo"),
        db.UniqueConstraint("id_configuracao", "escopo_default", name="uq_default_por_escopo"),
    )

    id = db.Column("id_configuracao_protocolo", BigIntPK, primary_key=True, autoincrement=True)
    id_configuracao = db.Column(
        db.BigInteger, db.ForeignKey("configuracao.id_configuracao"), nullable=False
    )
    id_protocolo = db.Column(
        db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"), nullable=True
    )
    em_uso = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        comment="0 = pausado pelo profissional; a escolha e preservada",
    )
    escopo_default = db.Column(
        db.Enum("triagem", "consulta", "ambos"),
        nullable=True,
        comment="NULL = nao e default; preenchido = default pessoal daquele escopo",
    )
    adicionado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    configuracao = db.relationship("Configuracao", back_populates="protocolos")
    protocolo = db.relationship("ProtocoloCatalogo")

    def to_dict(self):
        return {
            "id": self.id,
            "id_protocolo": self.id_protocolo,
            "uuid": self.protocolo.uuid if self.protocolo else None,
            "sigla": self.protocolo.sigla if self.protocolo else None,
            "nome": self.protocolo.nome_protocolo if self.protocolo else None,
            "tipo": self.protocolo.tipo_protocolo if self.protocolo else None,
            "em_uso": self.em_uso,
            "escopo_default": self.escopo_default,
            "adicionado_em": self.adicionado_em.isoformat() if self.adicionado_em else None,
            "configuracoes": self.configuracao.configuracoes_json if self.configuracao else None,
        }

    def __repr__(self):
        return f"<ConfiguracaoProtocolo {self.id}>"
