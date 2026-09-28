"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Novo (migration 2026-09-28): versao de um modulo, com configuracao e
explicacao versionadas. IMUTAVEL apos publicada: corrigir = criar
versao nova (mesmo padrao de ProtocoloVersao). Faixas numericas seguem
[min, max), imposto no schema Pydantic do configuracao_json, nao no banco.
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class ModuloVersao(db.Model):
    __tablename__ = "modulo_versao"

    id = db.Column("id_modulo_versao", BigIntPK, primary_key=True, autoincrement=True)
    id_modulo = db.Column(db.BigInteger, db.ForeignKey("catalogo_modulos.id_modulo"),
                           nullable=False)
    numero_versao = db.Column(db.String(20), nullable=False)
    configuracao_json = db.Column(db.JSON, nullable=False)
    explicacao_json = db.Column(db.JSON, nullable=False)
    status = db.Column(db.Enum("ativa", "descontinuada"), nullable=False, default="ativa")
    vigente_desde = db.Column(db.DateTime(timezone=True), nullable=False)
    vigente_ate = db.Column(db.DateTime(timezone=True), nullable=True)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("id_modulo", "numero_versao", name="uq_modulo_versao"),
        db.Index("ix_modulo_versao_status", "id_modulo", "status"),
        db.CheckConstraint("vigente_ate IS NULL OR vigente_ate > vigente_desde",
                            name="ck_modulo_versao_vigencia"),
    )

    modulo = db.relationship("CatalogoModulos", back_populates="versoes")
    campos = db.relationship("ModuloVersaoCampo", back_populates="modulo_versao",
                              cascade="all, delete-orphan", passive_deletes=True,
                              order_by="ModuloVersaoCampo.ordem")
    composicoes = db.relationship("ProtocoloComposicao", back_populates="modulo_versao")

    def to_dict(self):
        return {
            "id": self.id,
            "id_modulo": self.id_modulo,
            "numero_versao": self.numero_versao,
            "configuracao": self.configuracao_json,
            "explicacao": self.explicacao_json,
            "status": self.status,
            "vigente_desde": self.vigente_desde.isoformat() if self.vigente_desde else None,
            "vigente_ate": self.vigente_ate.isoformat() if self.vigente_ate else None,
            "observacoes": self.observacoes,
        }

    def __repr__(self):
        return f"<ModuloVersao modulo={self.id_modulo} v{self.numero_versao}>"