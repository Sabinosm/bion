"""
TipoJurisdicao — tabela de referência que substitui o antigo enum
tipo_regiao. Formaliza o conceito de jurisdição do FHIR/br-core
(Location.physicalType=jurisdiction), e facilita adicionar um novo
tipo no futuro sem precisar de ALTER TABLE (enum exige; tabela não).
"""

from src.models import db


class TipoJurisdicao(db.Model):
    __tablename__ = "tipo_jurisdicao"

    id = db.Column("id_tipo_jurisdicao", db.SmallInteger, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    display = db.Column(db.String(100), nullable=False)
    fhir_jurisdiction_level = db.Column(db.String(30), nullable=False)

    regioes = db.relationship("RegiaoGeografica", back_populates="tipo_jurisdicao")

    def to_dict(self):
        return {"codigo": self.codigo, "display": self.display}

    def __repr__(self):
        return f"<TipoJurisdicao {self.codigo}>"
