from datetime import datetime, timezone

from sqlalchemy.dialects.mysql import BIGINT

from src.models import db
from src.models.types import BigIntPK


class ProtocoloVersao(db.Model):
    __tablename__ = "protocolo_versao"

    __table_args__ = (
        db.UniqueConstraint("id_protocolo_catalogo", "numero_versao", name="uq_protocolo_versao"),
    )

    id = db.Column("id_versao", BigIntPK, primary_key=True, autoincrement=True)
    id_protocolo_catalogo = db.Column(
        db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"), nullable=False
    )
    numero_versao = db.Column(db.String(20), nullable=False)
    codigo_composicao = db.Column(
        db.BigInteger().with_variant(BIGINT(unsigned=True), "mysql"), unique=True, nullable=True
    )
    vigente_desde = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    vigente_ate = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(db.Enum("ativa", "descontinuada"), nullable=False, default="ativa")
    observacoes = db.Column(db.Text, nullable=True)
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="versoes")
    execucoes = db.relationship("InputProtocoloExecucao", back_populates="versao_utilizada")
    composicoes = db.relationship(
        "ProtocoloComposicao",
        back_populates="protocolo_versao",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProtocoloComposicao.ordem",
    )
    composicao_config = db.relationship(
        "ProtocoloComposicaoConfig",
        back_populates="protocolo_versao",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "numero_versao": self.numero_versao,
            "codigo_composicao": self.codigo_composicao,
            "vigente_desde": self.vigente_desde.isoformat() if self.vigente_desde else None,
            "vigente_ate": self.vigente_ate.isoformat() if self.vigente_ate else None,
            "status": self.status,
            "observacoes": self.observacoes,
        }

    def __repr__(self):
        return f"<ProtocoloVersao {self.id_protocolo_catalogo} v{self.numero_versao}>"
