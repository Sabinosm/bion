"""
Dominio Clinico (nucleo do ciclo de vida do atendimento/visita).

Conduta de enfermagem registrada dentro de um atendimento de triagem,
opcionalmente referenciando o protocolo do catalogo que a motivou.

INSERT-ONLY: o registro nunca é editado nem apagado; correção é uma nova
conduta. funcao_clinica guarda a função de quem escreveu NO MOMENTO da escrita
(o médico também pode registrar, pela regra de nível mínimo).
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
    funcao_clinica = db.Column(db.Enum("medico", "enfermeiro"), nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    atendimento = db.relationship("Atendimento", back_populates="condutas_enfermagem")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="condutas")
    profissional = db.relationship("Usuario", foreign_keys=[realizado_por])

    def to_dict(self):
        return {
            "atendimento_uuid": self.atendimento.uuid if self.atendimento else None,
            "protocolo_uuid": self.protocolo_catalogo.uuid if self.protocolo_catalogo else None,
            "descricao_conduta": self.descricao_conduta,
            "funcao_clinica": self.funcao_clinica,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    def __repr__(self):
        return f"<CondutaEnfermagem {self.id} atendimento={self.id_atendimento}>"