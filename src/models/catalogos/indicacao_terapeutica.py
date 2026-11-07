from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class IndicacaoTerapeutica(db.Model):
    __tablename__ = "indicacoes_terapeuticas"
    __table_args__ = (db.Index("idx_indicacao_nome", "nome"),)

    id = db.Column("id_indicacao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_indicacao",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    nome = db.Column(db.String(255), nullable=False, unique=True)
    sinonimos_busca_json = db.Column(db.JSON)

    medicamentos = db.relationship(
        "CatalogoMedicamentos",
        secondary="catalogo_medicamentos_indicacoes",
        back_populates="indicacoes_terapeuticas",
    )

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome": self.nome,
            "sinonimos_busca": self.sinonimos_busca_json,
        }

    def __repr__(self):
        return f"<IndicacaoTerapeutica {self.uuid} [{self.nome}]>"


catalogo_medicamentos_indicacoes = db.Table(
    "catalogo_medicamentos_indicacoes",
    db.Column(
        "id_catalogo",
        db.BigInteger,
        db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"),
        primary_key=True,
    ),
    db.Column(
        "id_indicacao",
        db.BigInteger,
        db.ForeignKey("indicacoes_terapeuticas.id_indicacao"),
        primary_key=True,
    ),
)
