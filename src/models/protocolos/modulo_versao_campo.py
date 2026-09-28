"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Novo (migration 2026-09-28): variaveis que uma versao de modulo consome.
Regra (validada no seed, nao no banco): as variaveis citadas no
configuracao_json da ModuloVersao devem ser exatamente as declaradas aqui.
"""

from src.models import db
from src.models.types import BigIntPK


class ModuloVersaoCampo(db.Model):
    __tablename__ = "modulo_versao_campo"

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    id_modulo_versao = db.Column(db.BigInteger,
                                  db.ForeignKey("modulo_versao.id_modulo_versao",
                                                ondelete="CASCADE"),
                                  nullable=False)
    id_variavel = db.Column(db.BigInteger, db.ForeignKey("variavel_clinica.id_variavel"),
                             nullable=False)
    obrigatorio = db.Column(db.Boolean, nullable=False, default=True)
    ordem = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("id_modulo_versao", "id_variavel", name="uq_modulo_versao_campo"),
        db.Index("ix_modulo_versao_campo_variavel", "id_variavel"),
    )

    modulo_versao = db.relationship("ModuloVersao", back_populates="campos")
    variavel = db.relationship("VariavelClinica", back_populates="usos_em_modulos")

    def to_dict(self):
        return {
            "id_variavel": self.id_variavel,
            "codigo": self.variavel.codigo if self.variavel else None,
            "obrigatorio": self.obrigatorio,
            "ordem": self.ordem,
        }

    def __repr__(self):
        return f"<ModuloVersaoCampo mv={self.id_modulo_versao} var={self.id_variavel}>"