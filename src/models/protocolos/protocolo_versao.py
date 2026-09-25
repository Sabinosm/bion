"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Novo: versionamento de protocolos. Cada linha representa uma versao
vigente/descontinuada de um ProtocoloCatalogo, permitindo que uma
execucao registre exatamente qual versao foi usada
(InputProtocoloExecucao.id_versao_utilizada).
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class ProtocoloVersao(db.Model):
    __tablename__ = "protocolo_versao"

    id = db.Column("id_versao", BigIntPK, primary_key=True, autoincrement=True)
    id_protocolo_catalogo = db.Column(db.BigInteger,
                                       db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"),
                                       nullable=False)
    numero_versao = db.Column(db.String(20), nullable=False)
    vigente_desde = db.Column(db.DateTime(timezone=True), nullable=False)
    vigente_ate = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(db.Enum("ativa", "descontinuada"), nullable=False, default="ativa")
    observacoes = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("id_protocolo_catalogo", "numero_versao",
                             name="uq_protocolo_versao"),
    )

    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="versoes")
    execucoes = db.relationship("InputProtocoloExecucao", back_populates="versao_utilizada")

    def to_dict(self):
        return {
            "id": self.id,
            "numero_versao": self.numero_versao,
            "vigente_desde": self.vigente_desde.isoformat() if self.vigente_desde else None,
            "vigente_ate": self.vigente_ate.isoformat() if self.vigente_ate else None,
            "status": self.status,
            "observacoes": self.observacoes,
        }

    def __repr__(self):
        return f"<ProtocoloVersao {self.id_protocolo_catalogo} v{self.numero_versao}>"