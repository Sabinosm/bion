from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class StepUpReautenticacao(db.Model):
    __tablename__ = "stepup_reautenticacao"

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, index=True
    )
    acao = db.Column(db.String(100), nullable=False)
    senha_confirmada = db.Column(db.Boolean, nullable=False, default=False)
    state = db.Column(db.String(64), unique=True, nullable=False)
    nonce = db.Column(db.String(64), nullable=False)
    expira_em = db.Column(db.DateTime(timezone=True), nullable=False)
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def expirado(self):
        expira_em = self.expira_em
        if expira_em.tzinfo is None:
            expira_em = expira_em.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expira_em

    def __repr__(self):
        return f"<StepUpReautenticacao usuario={self.id_usuario} acao={self.acao}>"
