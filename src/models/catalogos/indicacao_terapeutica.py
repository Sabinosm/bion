"""
Dominio Catalogo (medicamentos).

IndicacaoTerapeutica: lista curada e fechada de indicações comuns
(ex: "dor de cabeça", "febre", "inflamação"), usada para o médico
buscar medicamentos por sintoma/finalidade em vez de só por nome.
Somente-leitura para o usuário final -- mesmo padrão de curadoria do
CatalogoMedicamentos.

Relação N:N com CatalogoMedicamentos: um medicamento trata várias
indicações, uma indicação é tratada por vários medicamentos. A busca
funciona nos dois sentidos (sintoma -> medicamentos, e o inverso,
medicamento -> outras indicações que ele trata).
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class IndicacaoTerapeutica(db.Model):
    __tablename__ = "indicacoes_terapeuticas"
    __table_args__ = (
        db.Index("idx_indicacao_nome", "nome"),
    )

    id = db.Column("id_indicacao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_indicacao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome = db.Column(db.String(255), nullable=False, unique=True)
    # Termos alternativos para a mesma indicação, usados só para
    # ampliar a busca (ex: "cefaleia", "dor de cabeça", "enxaqueca"
    # todos apontam para a mesma linha). Não confundir com nomes de
    # medicamento -- isso é vocabulário de sintoma/finalidade.
    sinonimos_busca_json = db.Column(db.JSON)

    medicamentos = db.relationship(
        "CatalogoMedicamentos", secondary="catalogo_medicamentos_indicacoes",
        back_populates="indicacoes_terapeuticas")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome": self.nome,
            "sinonimos_busca": self.sinonimos_busca_json,
        }

    def __repr__(self):
        return f"<IndicacaoTerapeutica {self.uuid} [{self.nome}]>"


# Tabela associativa pura (sem atributos próprios) -- não precisa de
# classe/model dedicado, db.Table basta para relationship secondary.
catalogo_medicamentos_indicacoes = db.Table(
    "catalogo_medicamentos_indicacoes",
    db.Column("id_catalogo", db.BigInteger,
              db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"), primary_key=True),
    db.Column("id_indicacao", db.BigInteger,
              db.ForeignKey("indicacoes_terapeuticas.id_indicacao"), primary_key=True),
)