from datetime import datetime, timezone
from src.models import db
from src.models.types import BigIntPK


class StepUpToken(db.Model):
    __tablename__ = "stepup_token"

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"),
                            nullable=False, index=True)
    acao = db.Column(db.String(100), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expira_em = db.Column(db.DateTime(timezone=True), nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)