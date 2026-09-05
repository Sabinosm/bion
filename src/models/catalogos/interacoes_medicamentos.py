from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK

class InteracoesMedicamentos(db.Model):
    __tablename__ = "interacoes_medicamentos"
    __table_args__ = (
        # Evita cadastrar o mesmo par duas vezes (A-B e B-A são a mesma
        # interação). A aplicação deve sempre gravar com o menor id em
        # id_medicamento_a antes de inserir.
        db.UniqueConstraint("id_medicamento_a", "id_medicamento_b", name="uq_interacao_par"),
        # Lookup "quais interações envolvem o medicamento X" -- a query
        # sempre bate em um dos dois lados, então indexa os dois.
        db.Index("idx_interacao_medicamento_a", "id_medicamento_a"),
        db.Index("idx_interacao_medicamento_b", "id_medicamento_b"),
    )

    id = db.Column("id_interacao",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_interacao",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_medicamento_a = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    id_medicamento_b = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"))
    gravidade = db.Column(db.String(50))
    mecanismo_efeito = db.Column(db.Text)
    # Curto e direto, pensado para a IA usar em alerta ("evitar uso
    # concomitante", "monitorar função renal") -- mecanismo_efeito
    # explica o porquê, recomendacao diz o que fazer.
    recomendacao = db.Column(db.Text)

    medicamento_a = db.relationship("CatalogoMedicamentos", foreign_keys=[id_medicamento_a],
                                     back_populates="interacoes_como_a")
    medicamento_b = db.relationship("CatalogoMedicamentos", foreign_keys=[id_medicamento_b],
                                     back_populates="interacoes_como_b")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "gravidade": self.gravidade,
            "mecanismo_efeito": self.mecanismo_efeito,
            "recomendacao": self.recomendacao,
        }

    def __repr__(self):
        return f"<InteracoesMedicamentos {self.uuid}>"