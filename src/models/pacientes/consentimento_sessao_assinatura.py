"""
Sessão temporária de assinatura digital LGPD.
Tabela separada para não poluir consentimento_lgpd com tokens expirados.
"""

from datetime import datetime, timezone
import secrets
import hashlib

from src.models import db
from src.models.types import BigIntPK


class ConsentimentoSessaoAssinatura(db.Model):
    __tablename__ = "consentimento_sessao_assinatura"
    # Espelham os índices de migracao_refatoracao.sql (passo 5):
    # cancelar pendentes do paciente / limpeza por cron.
    __table_args__ = (
        db.Index("idx_sessao_paciente_status", "id_paciente", "status"),
        db.Index("idx_sessao_status_expira", "status", "expira_em"),
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    # Token criptográfico de 32 bytes em hex (64 chars) — impossível de adivinhar
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    # FK para o consentimento final (preenche só após assinatura bem-sucedida)
    id_consentimento = db.Column(db.BigInteger, db.ForeignKey("consentimento_lgpd.id_consentimento"), nullable=True)
    id_unidade = db.Column(db.Integer, nullable=False)  # ou FK para unidade/hospital
    id_medico_gerador = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    versao_termo = db.Column(db.String(50), nullable=False)
    # Caminho ou URL do PDF original do termo
    pdf_termo_path = db.Column(db.String(500), nullable=False)
    # Hash SHA-256 do PDF original — garante integridade
    hash_pdf_original = db.Column(db.String(64), nullable=False)
    # Snapshot do texto integral do termo no momento da geração
    texto_termo_snapshot = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expira_em = db.Column(db.DateTime(timezone=True), nullable=False)
    usado_em = db.Column(db.DateTime(timezone=True))
    # IP do médico no momento da geração (quem criou o link)
    ip_geracao = db.Column(db.String(45))
    # IP do paciente no momento da assinatura
    ip_assinatura = db.Column(db.String(45))
    # User-Agent do paciente
    user_agent_assinatura = db.Column(db.Text)
    # Geolocalização aproximada do IP do paciente (cidade/estado)
    geo_assinatura = db.Column(db.String(200))
    # Flag se a geoloc divergiu do hospital (não bloqueia, só registra)
    geo_divergente = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum("pendente", "usado", "expirado"), default="pendente", nullable=False)

    paciente = db.relationship("Paciente")
    consentimento = db.relationship("Consentimento")

    @staticmethod
    def gerar_token() -> str:
        """Gera token criptograficamente seguro de 64 caracteres hex."""
        return secrets.token_hex(32)

    @staticmethod
    def calcular_hash_pdf(caminho_pdf: str) -> str:
        """Calcula SHA-256 do arquivo PDF."""
        h = hashlib.sha256()
        with open(caminho_pdf, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def esta_expirado(self) -> bool:
        """MySQL costuma devolver datetime naive mesmo com timezone=True;
        gravamos sempre em UTC, então naive é tratado como UTC."""
        exp = self.expira_em
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp

    def __repr__(self):
        return f"<SessaoAssinatura token={self.token[:8]}... status={self.status}>"