"""
Dominio Catalogo.

Tabelas de referencia (nao-transacionais): catalogo de exames, catalogo
de medicamentos e interacoes conhecidas entre medicamentos. Eram stubs
no projeto original; completadas aqui.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


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





