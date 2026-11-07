from datetime import datetime, timezone
import secrets

from src.models import db
from src.models.types import BigIntPK


class ConsentimentoSessaoAssinatura(db.Model):
    __tablename__ = "consentimento_sessao_assinatura"
    __table_args__ = (
        db.Index("idx_sessao_paciente_status", "id_paciente", "status"),
        db.Index("idx_sessao_status_expira", "status", "expira_em"),
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    id_consentimento = db.Column(
        db.BigInteger, db.ForeignKey("consentimento_lgpd.id_consentimento"), nullable=True
    )
    id_unidade = db.Column(db.Integer, nullable=False)
    id_medico_gerador = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False
    )
    versao_termo = db.Column(db.String(50), nullable=False)
    hash_pdf_original = db.Column(db.String(64), nullable=False)
    texto_termo_snapshot = db.Column(db.Text, nullable=False)
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expira_em = db.Column(db.DateTime(timezone=True), nullable=False)
    usado_em = db.Column(db.DateTime(timezone=True))
    ip_geracao = db.Column(db.String(45))
    ip_assinatura = db.Column(db.String(45))
    user_agent_assinatura = db.Column(db.Text)
    geo_assinatura = db.Column(db.String(200))
    geo_divergente = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum("pendente", "usado", "expirado"), default="pendente", nullable=False)

    paciente = db.relationship("Paciente")
    consentimento = db.relationship("Consentimento")

    @staticmethod
    def gerar_token() -> str:
        return secrets.token_hex(32)

    def esta_expirado(self) -> bool:
        exp = self.expira_em
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp

    def __repr__(self):
        return f"<SessaoAssinatura token={self.token[:8]}... status={self.status}>"
