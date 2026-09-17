"""
CredencialTOTP — segundo fator via autenticador TOTP (Google/Microsoft
Authenticator), alternativo ao WebAuthn (ver credencial_webauthn.py).

Diferente de CredencialWebAuthn, um usuario tem no maximo 1 credencial
TOTP: reconfigurar substitui o secret existente na mesma linha, nunca
cria uma segunda.
"""

import os

from cryptography.fernet import Fernet

from src.models import db


# A key de criptografia do secret TOTP precisa ser fixa e persistida com
# seguranca (variavel de ambiente do deploy). Se mudar ou sumir, todo
# secret ja salvo fica ilegivel. O fallback abaixo (gerar key nova) so
# existe para nao quebrar em dev local; em producao a ausencia dessa env
# var deve ser tratada como erro de deploy.
_TOTP_ENCRYPTION_KEY = os.environ.get("TOTP_ENCRYPTION_KEY")
if not _TOTP_ENCRYPTION_KEY:
    _TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
_fernet = Fernet(_TOTP_ENCRYPTION_KEY.encode() if isinstance(_TOTP_ENCRYPTION_KEY, str) else _TOTP_ENCRYPTION_KEY)


class CredencialTOTP(db.Model):
    """
    Guarda o secret do autenticador TOTP, criptografado em repouso com
    Fernet (secret simetrico: quem o possui gera codigos validos). Nunca
    e exposto em resposta HTTP apos confirmado — ver to_dict().

    confirmado=False ate o usuario provar, no cadastro, que configurou
    corretamente e consegue gerar um codigo valido.
    """

    __tablename__ = "credencial_totp"

    id_credencial = db.Column(db.BigInteger, primary_key=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, unique=True, index=True
    )

    # Secret em base32, criptografado com Fernet antes de persistir.
    # Exposto na classe so via secret_plano (getter) e definir_secret
    # (setter), nunca diretamente.
    _secret_criptografado = db.Column("secret", db.String(255), nullable=False)

    confirmado = db.Column(db.Boolean, nullable=False, default=False)

    criado_em = db.Column(db.DateTime, server_default=db.func.now())

    @property
    def secret_plano(self) -> str:
        """Descriptografa o secret para verificacao (pyotp.TOTP(secret_plano).verify(codigo)).
        Nunca logar nem incluir em resposta HTTP.
        """
        return _fernet.decrypt(self._secret_criptografado.encode()).decode()

    def definir_secret(self, secret_plano: str) -> None:
        """Criptografa e grava um novo secret, no cadastro inicial ou numa reconfiguracao."""
        self._secret_criptografado = _fernet.encrypt(secret_plano.encode()).decode()

    def to_dict(self):
        """Representacao formatada para a tela de configuracoes. Nunca inclui o secret."""
        data_formatada = self.criado_em.strftime("%d/%m/%Y") if self.criado_em else ""

        return {
            "id_credencial": self.id_credencial,
            "confirmado": self.confirmado,
            "criado_em": data_formatada,
        }