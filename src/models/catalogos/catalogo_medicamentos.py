from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK

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