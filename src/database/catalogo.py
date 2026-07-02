"""
Dominio Catalogo.

Tabelas de referencia (nao-transacionais): catalogo de exames, catalogo
de medicamentos e interacoes conhecidas entre medicamentos. Eram stubs
no projeto original; completadas aqui.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.database import db
from src.database.types import BigIntPK


class CatalogoExames(db.Model):
    __tablename__ = "catalogo_exames"

    id = db.Column("id_catalogo_exame",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_catalogo_exame",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_exame = db.Column(db.String(255), nullable=False)
    codigo_tuss = db.Column(db.String(20))
    tipo = db.Column(db.Enum("laboratorial", "imagem", "funcional", "outro"))
    material = db.Column(db.String(100))
    jejum_horas = db.Column(db.SmallInteger)
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)

    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="catalogo_exame")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_exame": self.nome_exame,
            "codigo_tuss": self.codigo_tuss,
            "tipo": self.tipo,
            "material": self.material,
            "jejum_horas": self.jejum_horas,
            "ativo": self.ativo,
        }

    def __repr__(self):
        return f"<CatalogoExames {self.uuid} [{self.nome_exame}]>"


class CatalogoMedicamentos(db.Model):
    __tablename__ = "catalogo_medicamentos"

    id = db.Column("id_catalogo_medicamentos",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_catalogo_medicamentos",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    principio_ativo = db.Column(db.String(255))
    classe_farmaceutica = db.Column(db.String(255))
    nomes_comerciais_json = db.Column(db.JSON)

    medicamentos_em_uso = db.relationship("MedicamentoEmUso", back_populates="catalogo_medicamentos")
    prescricoes = db.relationship("Prescricao", back_populates="catalogo_medicamentos")
    interacoes_como_a = db.relationship(
        "InteracoesMedicamentos", foreign_keys="InteracoesMedicamentos.id_medicamento_a",
        back_populates="medicamento_a")
    interacoes_como_b = db.relationship(
        "InteracoesMedicamentos", foreign_keys="InteracoesMedicamentos.id_medicamento_b",
        back_populates="medicamento_b")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "principio_ativo": self.principio_ativo,
            "classe_farmaceutica": self.classe_farmaceutica,
            "nomes_comerciais": self.nomes_comerciais_json,
        }

    def __repr__(self):
        return f"<CatalogoMedicamentos {self.uuid} [{self.principio_ativo}]>"


class InteracoesMedicamentos(db.Model):
    __tablename__ = "interacoes_medicamentos"

    id = db.Column("id_interacao",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_interacao",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_medicamento_a = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    id_medicamento_b = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    gravidade = db.Column(db.String(50))
    mecanismo_efeito = db.Column(db.Text)

    medicamento_a = db.relationship("CatalogoMedicamentos", foreign_keys=[id_medicamento_a],
                                     back_populates="interacoes_como_a")
    medicamento_b = db.relationship("CatalogoMedicamentos", foreign_keys=[id_medicamento_b],
                                     back_populates="interacoes_como_b")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "gravidade": self.gravidade,
            "mecanismo_efeito": self.mecanismo_efeito,
        }

    def __repr__(self):
        return f"<InteracoesMedicamentos {self.uuid}>"
