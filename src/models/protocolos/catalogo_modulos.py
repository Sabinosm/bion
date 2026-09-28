"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Atualizado (migration 2026-09-28, MariaDB):
  - Removido campos_adicionados_json: os campos agora vivem em
    ModuloVersaoCampo (por versao do modulo).
  - Novas colunas: sigla, familia_calculo, tipo_saida, indice_bit,
    referencia_bibliografica.
  - Removida a relationship protocolos_personalizados (tabela
    protocolo_personalizado foi dropada); entra `versoes`.

Banco vazio (MariaDB): as colunas novas ja entram NOT NULL, sem backfill.

indice_bit (0..62) e a posicao do modulo no bitmask codigo_composicao
(ProtocoloVersao). tipo_saida e derivado da familia:
pontuador->pontos, classificador->categoria, regra->flag.
"""

from datetime import datetime, timezone
import uuid as _uuid

from sqlalchemy.dialects.mysql import SMALLINT

from src.models import db
from src.models.types import BigIntPK


class CatalogoModulos(db.Model):
    __tablename__ = "catalogo_modulos"

    id = db.Column("id_modulo", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_modulo", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_modulo = db.Column(db.String(255), nullable=False)
    sigla = db.Column(db.String(50), unique=True, nullable=False)
    tipo_modulo = db.Column(
        db.Enum("epidemiologico", "comorbidade", "faixa-etaria", "institucional"),
        nullable=False)
    familia_calculo = db.Column(db.Enum("pontuador", "classificador", "regra"), nullable=False)
    tipo_saida = db.Column(db.Enum("pontos", "categoria", "flag"), nullable=False)
    indice_bit = db.Column(db.SmallInteger().with_variant(SMALLINT(unsigned=True), "mysql"),
                            unique=True, nullable=False)
    status = db.Column(db.Enum("ativo", "inativo"), nullable=False, default="ativo")
    descricao = db.Column(db.Text)
    referencia_bibliografica = db.Column(db.Text)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.CheckConstraint("indice_bit BETWEEN 0 AND 62",
                            name="ck_catalogo_modulos_indice_bit_faixa"),
        db.CheckConstraint(
            "(familia_calculo = 'pontuador' AND tipo_saida = 'pontos') "
            "OR (familia_calculo = 'classificador' AND tipo_saida = 'categoria') "
            "OR (familia_calculo = 'regra' AND tipo_saida = 'flag')",
            name="ck_catalogo_modulos_saida_familia"),
    )

    versoes = db.relationship("ModuloVersao", back_populates="modulo",
                               cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_modulo": self.nome_modulo,
            "sigla": self.sigla,
            "tipo_modulo": self.tipo_modulo,
            "familia_calculo": self.familia_calculo,
            "tipo_saida": self.tipo_saida,
            "indice_bit": self.indice_bit,
            "status": self.status,
            "descricao": self.descricao,
        }

    def __repr__(self):
        return f"<CatalogoModulos {self.uuid} [{self.sigla}]>"