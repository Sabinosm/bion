"""
Dominio Catalogo (medicamentos).

Contraindicacao: lista curada e fechada de condições que contraindicam
o uso de um medicamento (ex: "gravidez", "insuficiência renal").
Deliberadamente SEM ligação com DoencaCronica/Alergia do paciente --
é vocabulário próprio do catálogo, curado e fechado, igual
IndicacaoTerapeutica. Cruzar com o quadro real do paciente é
responsabilidade de outra camada (ex: ao prescrever, comparar as
condições do paciente com essa lista), não do modelo em si.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Contraindicacao(db.Model):
    __tablename__ = "contraindicacoes"
    __table_args__ = (
        db.Index("idx_contraindicacao_nome", "nome"),
    )

    id = db.Column("id_contraindicacao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_contraindicacao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome = db.Column(db.String(255), nullable=False, unique=True)
    descricao = db.Column(db.Text)

    medicamentos = db.relationship(
        "CatalogoMedicamentos", secondary="catalogo_medicamentos_contraindicacoes",
        back_populates="contraindicacoes")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome": self.nome,
            "descricao": self.descricao,
        }

    def __repr__(self):
        return f"<Contraindicacao {self.uuid} [{self.nome}]>"


catalogo_medicamentos_contraindicacoes = db.Table(
    "catalogo_medicamentos_contraindicacoes",
    db.Column("id_catalogo", db.BigInteger,
              db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"), primary_key=True),
    db.Column("id_contraindicacao", db.BigInteger,
              db.ForeignKey("contraindicacoes.id_contraindicacao"), primary_key=True),
)