from datetime import datetime, timezone
import uuid as _uuid

from sqlalchemy.ext.hybrid import hybrid_property

from src.models import db
from src.models.types import BigIntPK

_FK_USUARIO = "usuarios.id_usuario"
_FK_ATENDIMENTO = "atendimento.id_atendimento"


class MedicamentoEmUso(db.Model):
    __tablename__ = "medicamentos_em_uso"
    __table_args__ = (
        db.Index("idx_medicamento_em_uso_deletado", "deletado"),
        db.Index("idx_medicamento_em_uso_paciente_deletado", "id_paciente", "deletado"),
    )

    id = db.Column("id_medicamentos_uso", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_medicamentos_uso",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_paciente = db.Column(
        db.BigInteger, db.ForeignKey("paciente.id_paciente", ondelete="RESTRICT"), nullable=False
    )
    id_catalogo = db.Column(
        db.BigInteger,
        db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos", ondelete="RESTRICT"),
        nullable=True,
    )
    descricao = db.Column(db.Text, nullable=False)
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    desde = db.Column(db.Date)
    ate = db.Column(db.Date, nullable=True)
    status_uso = db.Column(
        db.Enum("ativo", "interrompido", "concluido"),
        nullable=False,
        default="ativo",
        server_default="ativo",
    )
    criado_por = db.Column(
        db.BigInteger, db.ForeignKey(_FK_USUARIO, ondelete="RESTRICT"), nullable=True
    )
    id_atendimento_origem = db.Column(
        db.BigInteger, db.ForeignKey(_FK_ATENDIMENTO, ondelete="RESTRICT"), nullable=True
    )
    encerrado_por = db.Column(
        db.BigInteger, db.ForeignKey(_FK_USUARIO, ondelete="RESTRICT"), nullable=True
    )
    id_atendimento_encerramento = db.Column(
        db.BigInteger, db.ForeignKey(_FK_ATENDIMENTO, ondelete="RESTRICT"), nullable=True
    )
    id_substituida_por = db.Column(
        db.BigInteger,
        db.ForeignKey("medicamentos_em_uso.id_medicamentos_uso", ondelete="RESTRICT"),
        nullable=True,
    )
    deletado = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    deletado_em = db.Column(db.DateTime(timezone=True), nullable=True)
    motivo_delete = db.Column(
        db.Enum(
            "erro-digitacao",
            "registro-duplicado",
            "diagnostico-incorreto",
            "solicitacao-paciente",
            "outro",
        ),
        nullable=True,
    )
    observacoes_delete = db.Column(db.Text, nullable=True)
    deletado_por = db.Column(
        db.BigInteger, db.ForeignKey(_FK_USUARIO, ondelete="RESTRICT"), nullable=True
    )
    id_atendimento_delecao = db.Column(
        db.BigInteger, db.ForeignKey(_FK_ATENDIMENTO, ondelete="RESTRICT"), nullable=True
    )

    paciente = db.relationship("Paciente", back_populates="medicamentos_em_uso")
    atendimento_origem = db.relationship(
        "Atendimento", foreign_keys=[id_atendimento_origem], viewonly=True
    )
    catalogo_medicamentos = db.relationship(
        "CatalogoMedicamentos", back_populates="medicamentos_em_uso"
    )

    @hybrid_property
    def ativo(self):
        return self.status_uso == "ativo" and not self.deletado

    @ativo.expression
    def ativo(cls):
        return db.and_(cls.status_uso == "ativo", cls.deletado == False)

    def to_dict(self):
        catalogo = self.catalogo_medicamentos
        return {
            "uuid": self.uuid,
            "descricao": self.descricao,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "desde": self.desde.isoformat() if self.desde else None,
            "ate": self.ate.isoformat() if self.ate else None,
            "status_uso": self.status_uso,
            "uuid_atendimento_origem": (
                self.atendimento_origem.uuid if self.atendimento_origem else None
            ),
            "ativo": bool(self.ativo),
            "catalogo": (
                {
                    "uuid": catalogo.uuid,
                    "principio_ativo": catalogo.principio_ativo,
                }
                if catalogo
                else None
            ),
            "verificavel_interacoes": self.id_catalogo is not None,
        }

    def __repr__(self):
        return f"<MedicamentoEmUso {self.uuid}>"
