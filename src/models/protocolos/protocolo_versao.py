"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Novo (migration 2026-09-28): substitui ProtocoloPersonalizado. A
composicao pertence a uma VERSAO do protocolo e referencia VERSOES de
modulo (nunca o modulo "solto"). "ordem" e so exibicao; o motor nao
depende dela.

Regras que ficam fora do model (ver verificacoes V1..V5 da migration):
  - o mesmo modulo nao pode aparecer em duas versoes na mesma composicao
    (o bitmask nao distingue versao);
  - agregacao deve ser compativel com o tipo_saida dos modulos do grupo.
"""

from src.models import db
from src.models.types import BigIntPK


class ProtocoloComposicao(db.Model):
    __tablename__ = "protocolo_composicao"

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    id_protocolo_versao = db.Column(db.BigInteger,
                                     db.ForeignKey("protocolo_versao.id_versao",
                                                   ondelete="CASCADE"),
                                     nullable=False)
    id_modulo_versao = db.Column(db.BigInteger,
                                  db.ForeignKey("modulo_versao.id_modulo_versao"),
                                  nullable=False)
    papel = db.Column(db.Enum("principal", "gatilho", "informativo"),
                       nullable=False, default="principal")
    grupo_agregacao = db.Column(db.String(50))
    ordem = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("id_protocolo_versao", "id_modulo_versao",
                             name="uq_protocolo_composicao"),
        db.Index("ix_protocolo_composicao_modulo", "id_modulo_versao"),
        # gatilho nao participa de agregacao (ele decide aplicabilidade)
        db.CheckConstraint("papel <> 'gatilho' OR grupo_agregacao IS NULL",
                            name="ck_pc_gatilho_sem_grupo"),
    )

    protocolo_versao = db.relationship("ProtocoloVersao", back_populates="composicoes")
    modulo_versao = db.relationship("ModuloVersao", back_populates="composicoes")

    def to_dict(self):
        return {
            "id_modulo_versao": self.id_modulo_versao,
            "papel": self.papel,
            "grupo_agregacao": self.grupo_agregacao,
            "ordem": self.ordem,
        }

    def __repr__(self):
        return f"<ProtocoloComposicao pv={self.id_protocolo_versao} mv={self.id_modulo_versao}>"