import os

from cryptography.fernet import Fernet

from src.models import db

_TOTP_ENCRYPTION_KEY = os.environ.get("TOTP_ENCRYPTION_KEY")
if not _TOTP_ENCRYPTION_KEY:
    _TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
_fernet = Fernet(
    _TOTP_ENCRYPTION_KEY.encode() if isinstance(_TOTP_ENCRYPTION_KEY, str) else _TOTP_ENCRYPTION_KEY
)


class CredencialTOTP(db.Model):
    __tablename__ = "credencial_totp"

    id_credencial = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, unique=True, index=True
    )
    _secret_criptografado = db.Column("secret", db.String(255), nullable=False)
    confirmado = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime, server_default=db.func.now())

    @property
    def secret_plano(self) -> str:
        return _fernet.decrypt(self._secret_criptografado.encode()).decode()

    def definir_secret(self, secret_plano: str) -> None:
        self._secret_criptografado = _fernet.encrypt(secret_plano.encode()).decode()

    def to_dict(self):
        data_formatada = self.criado_em.strftime("%d/%m/%Y") if self.criado_em else ""

        return {
            "id_credencial": self.id_credencial,
            "confirmado": self.confirmado,
            "criado_em": data_formatada,
        }
