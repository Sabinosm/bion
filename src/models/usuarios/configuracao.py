"""
Configuracao — preferencias do usuario (tema, fonte, idioma) e vinculo
com os protocolos que ele acompanha, guardados em configuracoes_json.
Relacao 1-para-1 com Usuario.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Configuracao(db.Model):
    __tablename__ = "configuracao"

    id = db.Column("id_configuracao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_configuracao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"),
                            unique=True, nullable=False)
    configuracoes_json = db.Column(db.JSON)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario", back_populates="configuracao")
    protocolos = db.relationship("ConfiguracaoProtocolo", back_populates="configuracao",
                                  cascade="all, delete-orphan")

    def to_dict(self):
        """
        Espera configuracoes_json no formato:
        {
            "design": {"tema": "claro", "tamanho_fonte": "medio"},
            "preferencias": {"linguagem": ["pt-BR"]}
        }
        """
        return {
            "uuid": self.uuid,
            "design": self.configuracoes_json["design"],
            "preferencias": self.configuracoes_json["preferencias"],
            "protocolos": {
                (p.protocolo.sigla if p.protocolo else p.id_protocolo): {
                    "nome": p.protocolo.nome_protocolo if p.protocolo else None,
                    "tipo": p.protocolo.tipo_protocolo if p.protocolo else None,
                    "id": p.id_protocolo,
                }
                for p in self.protocolos
            }
        }

    def __repr__(self):
        return f"<Configuracao {self.uuid}>"