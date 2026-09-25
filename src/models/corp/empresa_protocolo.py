"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Teto institucional: quais protocolos do catalogo uma empresa libera para
uso, com governanca (MIGRATION 2, 2026-09-24):
  - escopo_default_institucional: fallback do default pessoal
    (configuracao_protocolo.escopo_default) quando o profissional nao
    tem uma escolha propria para aquele escopo. No maximo um default
    institucional por escopo por empresa (UNIQUE com NULL).
  - politica: 'obrigatorio' impede o profissional de desligar
    (em_uso = 0) sua propria configuracao para este protocolo.
  - aprovado_por / aprovado_em: registro de governanca clinica exigido
    sempre que 'ativo', 'politica' ou o default institucional mudam.

NOTA: as convencoes abaixo nao sao impostas por CHECK (MySQL 8 nao
suporta CHECK com subquery) e devem ser validadas na camada de servico:
  1. escopo_default_institucional preenchido exige ativo = 1.
  2. politica = 'obrigatorio' exige ativo = 1.
  3. mudanca em ativo/politica/default institucional exige
     aprovado_por e aprovado_em preenchidos.
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class EmpresaProtocolo(db.Model):
    __tablename__ = "empresa_protocolo"

    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"),
                            primary_key=True)
    id_protocolo_catalogo = db.Column(db.BigInteger,
                                       db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"),
                                       primary_key=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    atualizado_em = db.Column(db.DateTime(timezone=True),
                               default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc),
                               nullable=False)

    escopo_default_institucional = db.Column(
        db.Enum("triagem", "consulta", "ambos"), nullable=True,
        comment="NULL = nao e default; preenchido = default institucional daquele escopo")
    politica = db.Column(db.Enum("obrigatorio", "opcional"), nullable=False, default="opcional",
                          comment="obrigatorio: profissional nao pode desligar (em_uso=0) na sua preferencia")
    aprovado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=True,
                              comment="quem da governanca clinica aprovou a liberacao/alteracao")
    aprovado_em = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("id_empresa", "escopo_default_institucional",
                             name="uq_emp_default_por_escopo"),
    )

    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="empresas")
    empresa = db.relationship("Empresas", foreign_keys=[id_empresa])
    aprovador = db.relationship("Usuarios", foreign_keys=[aprovado_por])

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
        return f"<EmpresaProtocolo empresa={self.id_empresa} protocolo={self.id_protocolo_catalogo}>"