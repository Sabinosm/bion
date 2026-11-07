from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class EmpresaProtocolo(db.Model):
    __tablename__ = "empresa_protocolo"

    __table_args__ = (
        db.UniqueConstraint(
            "id_empresa", "escopo_default_institucional", name="uq_emp_default_por_escopo"
        ),
    )

    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), primary_key=True)
    id_protocolo_catalogo = db.Column(
        db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"), primary_key=True
    )
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    atualizado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    escopo_default_institucional = db.Column(
        db.Enum("triagem", "consulta", "ambos"),
        nullable=True,
        comment="NULL = nao e default; preenchido = default institucional daquele escopo",
    )
    politica = db.Column(
        db.Enum("obrigatorio", "opcional"),
        nullable=False,
        default="opcional",
        comment="obrigatorio: profissional nao pode desligar (em_uso=0) na sua preferencia",
    )
    aprovado_por = db.Column(
        db.BigInteger,
        db.ForeignKey("usuarios.id_usuario"),
        nullable=True,
        comment="quem da governanca clinica aprovou a liberacao/alteracao",
    )
    aprovado_em = db.Column(db.DateTime(timezone=True), nullable=True)

    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="empresas")
    empresa = db.relationship("Empresa", foreign_keys=[id_empresa])
    aprovador = db.relationship("Usuario", foreign_keys=[aprovado_por])

    def to_dict(self):
        return {
            "id_empresa": self.id_empresa,
            "id_protocolo_catalogo": self.id_protocolo_catalogo,
            "ativo": self.ativo,
            "escopo_default_institucional": self.escopo_default_institucional,
            "politica": self.politica,
            "aprovado_por": self.aprovado_por,
            "aprovado_em": self.aprovado_em.isoformat() if self.aprovado_em else None,
        }

    def __repr__(self):
        return (
            f"<EmpresaProtocolo empresa={self.id_empresa} protocolo={self.id_protocolo_catalogo}>"
        )
