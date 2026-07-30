"""
ALTERADO: tipo_regiao (enum) substituído por id_tipo_jurisdicao (FK para
TipoJurisdicao). Mantida @property `tipo_regiao` para que código
existente que lê `regiao.tipo_regiao` continue funcionando sem alteração
(mesmo padrão já usado em Usuario.tipo_usuario e Empresa.cnpj).
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class RegiaoGeografica(db.Model):
    __tablename__ = "regiao_geografica"

    id = db.Column("id_regiao_geografica", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_regiao = db.Column(db.String(255), nullable=False)

    # tipo_regiao REMOVIDO como enum -- ver id_tipo_jurisdicao + property abaixo
    id_tipo_jurisdicao = db.Column(db.SmallInteger, db.ForeignKey("tipo_jurisdicao.id_tipo_jurisdicao"),
                                     nullable=False)

    id_regiao_pai = db.Column("id_regiao_pai", db.BigInteger, db.ForeignKey("regiao_geografica.id_regiao_geografica"))

    codigo_ibge = db.Column(db.String(20), unique=True)
    uf = db.Column(db.String(2))
    latitude_centroide = db.Column(db.Numeric(10, 8))
    longitude_centroide = db.Column(db.Numeric(11, 8))
    populacao_estimada = db.Column(db.Integer)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    regioes_filhas = db.relationship(
        "RegiaoGeografica",
        primaryjoin="RegiaoGeografica.id == RegiaoGeografica.id_regiao_pai",
        backref=db.backref("regiao_pai", remote_side="RegiaoGeografica.id"),
    )

    empresas = db.relationship("Empresa", back_populates="regiao_geografica")
    pacientes = db.relationship("Paciente", back_populates="regiao_geografica")
    tipo_jurisdicao_ref = db.relationship(
        "TipoJurisdicao",
        primaryjoin="RegiaoGeografica.id_tipo_jurisdicao == TipoJurisdicao.id",
        back_populates="regioes",
    )

    @property
    def tipo_regiao(self):
        """Leitura de compatibilidade: `regiao.tipo_regiao` continua
        retornando a mesma string de antes (ex: 'municipio'), sem
        precisar tocar em código que já lê esse atributo."""
        return self.tipo_jurisdicao_ref.codigo if self.tipo_jurisdicao_ref else None

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_regiao": self.nome_regiao,
            "tipo_regiao": self.tipo_regiao,
            "codigo_ibge": self.codigo_ibge,
            "uf": self.uf,
            "populacao_estimada": self.populacao_estimada,
        }

    def __repr__(self):
        return f"<RegiaoGeografica {self.uuid} [{self.tipo_regiao}]>"