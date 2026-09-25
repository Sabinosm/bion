"""
Dominio Clinico (nucleo do ciclo de vida do atendimento/visita).

Novo: conduta de enfermagem registrada dentro de um atendimento,
opcionalmente referenciando o protocolo do catalogo que a motivou.
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class CondutaEnfermagem(db.Model):
    __tablename__ = "conduta_enfermagem"

    id = db.Column("id_conduta", BigIntPK, primary_key=True, autoincrement=True)
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"),
                                nullable=False)
    id_protocolo_catalogo = db.Column(db.BigInteger,
                                       db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"),
                                       nullable=True)
    descricao_conduta = db.Column(db.Text, nullable=False)
    realizado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    atendimento = db.relationship("Atendimento", back_populates="condutas_enfermagem")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="condutas")
    profissional = db.relationship("Usuarios", foreign_keys=[realizado_por])

    def to_dict(self):
        return {
            "id": self.id,
            "descricao_conduta": self.descricao_conduta,
            "realizado_por": self.realizado_por,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    def __repr__(self):
        return f"<CondutaEnfermagem {self.id} atendimento={self.id_atendimento}>"