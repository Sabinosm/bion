from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK

class CatalogoMedicamentos(db.Model):
    __tablename__ = "catalogo_medicamentos"
    __table_args__ = (
        # principio_ativo é o campo mais buscado (join com prescrição,
        # busca do médico, cruzamento com fonte externa na sincronização)
        db.Index("idx_catalogo_principio_ativo", "principio_ativo"),
    )

    id = db.Column("id_catalogo_medicamentos",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_catalogo_medicamentos",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    principio_ativo = db.Column(db.String(255))
    classe_farmaceutica = db.Column(db.String(255))
    nomes_comerciais_json = db.Column(db.JSON)

    # Rastreabilidade: de onde veio o registro e quando foi checado
    # pela última vez contra essa fonte. Base para o botão de
    # verificação/sincronização -- não sobrescreve automático, só
    # sinaliza divergência.
    fonte_origem = db.Column(db.String(255))
    ultima_verificacao_em = db.Column(db.DateTime(timezone=True))

    medicamentos_em_uso = db.relationship("MedicamentoEmUso", back_populates="catalogo_medicamentos")
    prescricoes = db.relationship("Prescricao", back_populates="catalogo_medicamentos")
    interacoes_como_a = db.relationship(
        "InteracoesMedicamentos", foreign_keys="InteracoesMedicamentos.id_medicamento_a",
        back_populates="medicamento_a")
    interacoes_como_b = db.relationship(
        "InteracoesMedicamentos", foreign_keys="InteracoesMedicamentos.id_medicamento_b",
        back_populates="medicamento_b")
    indicacoes_terapeuticas = db.relationship(
        "IndicacaoTerapeutica", secondary="catalogo_medicamentos_indicacoes",
        back_populates="medicamentos")
    contraindicacoes = db.relationship(
        "Contraindicacao", secondary="catalogo_medicamentos_contraindicacoes",
        back_populates="medicamentos")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "principio_ativo": self.principio_ativo,
            "classe_farmaceutica": self.classe_farmaceutica,
            "nomes_comerciais": self.nomes_comerciais_json,
            "fonte_origem": self.fonte_origem,
            "ultima_verificacao_em": self.ultima_verificacao_em.isoformat()
            if self.ultima_verificacao_em else None,
            "indicacoes_terapeuticas": [i.nome for i in self.indicacoes_terapeuticas],
            "contraindicacoes": [c.nome for c in self.contraindicacoes],
        }

    def __repr__(self):
        return f"<CatalogoMedicamentos {self.uuid} [{self.principio_ativo}]>"