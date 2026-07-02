"""
Dominio Corporativo / Regional.

Empresa e o tenant (instituicao/cliente) em um sistema multi-tenant.
RegiaoGeografica e a hierarquia territorial (pais > estado > ... > distrito
sanitario) usada para localizar empresas e pacientes para fins
epidemiologicos.

Os models originais (app/empresa/model.py, app/regiao/model.py) eram
stubs com apenas id/uuid/criado_em. Completados aqui com os campos
mapeados no schema do projeto (analise.md / UML).
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.database import db
from src.database.types import BigIntPK


class RegiaoGeografica(db.Model):
    __tablename__ = "regiao_geografica"

    id = db.Column("id_regiao_geografica", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_regiao = db.Column(db.String(255), nullable=False)
    tipo_regiao = db.Column(
        db.Enum("pais", "estado", "mesorregiao", "microrregiao",
                "municipio", "distrito-sanitario"),
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


class Empresa(db.Model):
    __tablename__ = "empresa"

    id = db.Column("id_empresa", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_empresa", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_fantasia = db.Column(db.String(255), nullable=False)
    razao_social = db.Column(db.String(255))
    cnpj = db.Column(db.String(20), unique=True, nullable=False)
    numero = db.Column(db.String(50))
    bairro = db.Column(db.String(100))
    complemento = db.Column(db.String(150))
    cep = db.Column(db.String(20))
    id_regiao_geografica = db.Column(db.BigInteger, db.ForeignKey("regiao_geografica.id_regiao_geografica"))
    status_plano = db.Column(db.String(50))
    plano = db.Column(db.String(100))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="empresas")
    usuarios = db.relationship("Usuario", back_populates="empresa",
                                cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_fantasia": self.nome_fantasia,
            "razao_social": self.razao_social,
            "cnpj": self.cnpj,
            "status_plano": self.status_plano,
            "plano": self.plano,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    def __repr__(self):
        return f"<Empresa {self.uuid} [{self.nome_fantasia}]>"
