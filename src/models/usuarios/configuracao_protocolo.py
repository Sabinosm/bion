"""
ConfiguracaoProtocolo — vincula uma Configuracao (preferencias de um
usuario) a um protocolo do catalogo, permitindo overrides por protocolo.

Atualizado pela MIGRATION 3 (2026-09-24): a linha deixa de significar
apenas "esta na configuracao = escolhido" e passa a responder:
  - em_uso: escolhido mas pausado (0), sem perder a escolha/historico.
  - escopo_default: default PESSOAL do usuario para aquele escopo
    (triagem/consulta/ambos). NULL = nao e default. UNIQUE por
    (id_configuracao, escopo_default) -- MySQL permite varios NULLs,
    entao o banco ja garante no maximo um default pessoal por escopo
    por usuario.
  - adicionado_em: auditoria basica de quando o protocolo entrou na
    configuracao do usuario.

A UNIQUE antiga em id_configuracao (sozinho) foi trocada por
uq_config_protocolo (id_configuracao, id_protocolo), permitindo mais de
um protocolo por configuracao.

Convencoes de aplicacao (nao impostas por CHECK, validar no service):
  1. Ao marcar um novo escopo_default, zerar o anterior do mesmo escopo
     na MESMA transacao.
  2. em_uso = 0 e recusado quando EmpresaProtocolo.politica = 'obrigatorio'.
  3. escopo_default so pode ser preenchido quando o protocolo consta do
     catalogo efetivo (liberado pela empresa + em_uso = 1).
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class ConfiguracaoProtocolo(db.Model):
    __tablename__ = "configuracao_protocolo"

    id = db.Column("id_configuracao_protocolo", BigIntPK, primary_key=True, autoincrement=True)
    id_configuracao = db.Column(db.BigInteger, db.ForeignKey("configuracao.id_configuracao"),
                                 nullable=False)
    id_protocolo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"),
                              nullable=True)

    em_uso = db.Column(db.Boolean, nullable=False, default=True,
                        comment="0 = pausado pelo profissional; a escolha e preservada")
    escopo_default = db.Column(
        db.Enum("triagem", "consulta", "ambos"), nullable=True,
        comment="NULL = nao e default; preenchido = default pessoal daquele escopo")
    adicionado_em = db.Column(db.DateTime(timezone=True),
                               default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("id_configuracao", "id_protocolo", name="uq_config_protocolo"),
        db.UniqueConstraint("id_configuracao", "escopo_default", name="uq_default_por_escopo"),
    )

    configuracao = db.relationship("Configuracao", back_populates="protocolos")
    protocolo = db.relationship("ProtocoloCatalogo")

    def to_dict(self):
        return {
            "id": self.id,
            "id_protocolo": self.id_protocolo,
            "nome": self.protocolo.nome_protocolo if self.protocolo else None,
            "tipo": self.protocolo.tipo_protocolo if self.protocolo else None,
            "em_uso": self.em_uso,
            "escopo_default": self.escopo_default,
            "adicionado_em": self.adicionado_em.isoformat() if self.adicionado_em else None,
            "configuracoes": self.configuracao.configuracoes_json if self.configuracao else None,
        }

    def __repr__(self):
        return f"<ConfiguracaoProtocolo {self.id}>"