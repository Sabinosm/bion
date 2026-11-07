from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK
import uuid as _uuid


class ReacaoAlergia(db.Model):
    __tablename__ = "reacao_alergia"
    __table_args__ = (db.Index("idx_reacao_alergia_alergia_deletado", "id_alergia", "deletado"),)

    id = db.Column("id_reacao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_reacao",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_alergia = db.Column(
        db.BigInteger, db.ForeignKey("alergia.id_alergia", ondelete="RESTRICT"), nullable=False
    )
    manifestacao = db.Column(
        db.Enum(
            "cutanea",
            "respiratoria",
            "anafilaxia",
            "gastrointestinal",
            "cardiovascular",
            "sistemica",
        ),
        nullable=False,
    )
    gravidade = db.Column(db.Enum("leve", "moderada", "grave"), nullable=False)
    descricao = db.Column(db.Text)
    data_ocorrencia = db.Column(db.Date, nullable=True)
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    criado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    id_atendimento_origem = db.Column(
        db.BigInteger, db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT")
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
        db.BigInteger, db.ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=True
    )
    id_atendimento_delecao = db.Column(
        db.BigInteger,
        db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT"),
        nullable=True,
    )

    alergia = db.relationship("Alergia", back_populates="reacoes")
    usuario_criacao = db.relationship("Usuario", foreign_keys=[criado_por])

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "manifestacao": self.manifestacao,
            "gravidade": self.gravidade,
            "descricao": self.descricao,
            "data_ocorrencia": self.data_ocorrencia.isoformat() if self.data_ocorrencia else None,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "criado_por": self.usuario_criacao.nome_completo if self.usuario_criacao else None,
        }

    def __repr__(self):
        return f"<ReacaoAlergia {self.uuid} [{self.manifestacao}]>"
