"""
ConfiguracaoProtocolo — vincula uma Configuracao (preferencias de um
usuario) a um protocolo do catalogo, permitindo overrides por protocolo.
"""

from src.models import db
from src.models.types import BigIntPK


class ConfiguracaoProtocolo(db.Model):
    __tablename__ = "configuracao_protocolo"

    id = db.Column("id_configuracao_protocolo", BigIntPK, primary_key=True, autoincrement=True)
    id_configuracao = db.Column(db.BigInteger, db.ForeignKey("configuracao.id_configuracao"),
                                 nullable=False)
    id_protocolo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"),
                              nullable=True)

    configuracao = db.relationship("Configuracao", back_populates="protocolos")
    protocolo = db.relationship("ProtocoloCatalogo")

    def to_dict(self):
        return {
            "id": self.id,
            "id_protocolo": self.id_protocolo,
            "nome": self.protocolo.nome_protocolo if self.protocolo else None,
            "tipo": self.protocolo.tipo_protocolo if self.protocolo else None,
            "configuracoes": self.configuracao.configuracoes_json if self.configuracao else None,
        }

    def __repr__(self):
        return f"<ConfiguracaoProtocolo {self.id}>"