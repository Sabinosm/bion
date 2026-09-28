"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Novo (migration 2026-09-28): dicionario compartilhado de variaveis
clinicas. Modulos consomem variaveis daqui via ModuloVersaoCampo.

Convencoes:
  - codigo: estavel e legivel (minusculas, digitos e underscore).
  - categorico exige opcoes_json; numerico/booleano nao tem opcoes.
  - valor_min/valor_max (plausibilidade) so para numerico.
Todo conteudo entra por SEED.
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class VariavelClinica(db.Model):
    __tablename__ = "variavel_clinica"

    id = db.Column("id_variavel", BigIntPK, primary_key=True, autoincrement=True)
    codigo = db.Column(db.String(100), unique=True, nullable=False)
    nome = db.Column(db.String(255), nullable=False)
    tipo_dado = db.Column(db.Enum("numerico", "categorico", "booleano"), nullable=False)
    unidade = db.Column(db.String(30))
    opcoes_json = db.Column(db.JSON)
    valor_min = db.Column(db.Numeric(14, 4))
    valor_max = db.Column(db.Numeric(14, 4))
    codigo_loinc = db.Column(db.String(50))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.CheckConstraint("codigo REGEXP '^[a-z][a-z0-9_]*$'",
                            name="ck_variavel_codigo_formato"),
        db.CheckConstraint(
            "(tipo_dado = 'categorico' AND opcoes_json IS NOT NULL) "
            "OR (tipo_dado <> 'categorico' AND opcoes_json IS NULL)",
            name="ck_variavel_opcoes_coerentes"),
        db.CheckConstraint(
            "tipo_dado = 'numerico' OR (valor_min IS NULL AND valor_max IS NULL)",
            name="ck_variavel_limites_numerico"),
        db.CheckConstraint(
            "valor_min IS NULL OR valor_max IS NULL OR valor_min < valor_max",
            name="ck_variavel_limites_ordem"),
    )

    usos_em_modulos = db.relationship("ModuloVersaoCampo", back_populates="variavel")

    def to_dict(self):
        return {
            "codigo": self.codigo,
            "nome": self.nome,
            "tipo_dado": self.tipo_dado,
            "unidade": self.unidade,
            "opcoes": self.opcoes_json,
            "valor_min": float(self.valor_min) if self.valor_min is not None else None,
            "valor_max": float(self.valor_max) if self.valor_max is not None else None,
            "codigo_loinc": self.codigo_loinc,
        }

    def __repr__(self):
        return f"<VariavelClinica {self.codigo}>"