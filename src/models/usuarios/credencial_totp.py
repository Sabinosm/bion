"""
Credencial TOTP (autenticador tipo Google/Microsoft Authenticator),
segundo fator alternativo ao WebAuthn -- ver credencial_webauthn.py
para o outro método.

ADICIONAR ao mesmo módulo de domínio de Usuarios (junto de
CredencialWebAuthn), mantendo a mesma convenção de nomes e tipos.
"""

import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from src.models import db


# A key de criptografia do secret TOTP PRECISA ser fixa e persistida
# com segurança (variável de ambiente do deploy, nunca hardcode nem
# gerada em runtime em produção) -- se ela mudar ou sumir, todo
# secret já salvo fica ilegível e o usuário perde o TOTP cadastrado
# sem aviso. O fallback abaixo (gerar uma key nova se a env var não
# existir) só existe para não quebrar em dev local; em produção a
# ausência dessa env var deveria ser tratada como erro de deploy.

_TOTP_ENCRYPTION_KEY = os.environ.get("TOTP_ENCRYPTION_KEY")
if not _TOTP_ENCRYPTION_KEY:
    _TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
_fernet = Fernet(_TOTP_ENCRYPTION_KEY.encode() if isinstance(_TOTP_ENCRYPTION_KEY, str) else _TOTP_ENCRYPTION_KEY)


class CredencialTOTP(db.Model):
    """
    Guarda o SECRET (criptografado) do autenticador TOTP do usuário.

    Diferente de CredencialWebAuthn, não existe "várias linhas por
    usuário" aqui -- um usuário tem no máximo 1 CredencialTOTP.
    Reconfigurar substitui o secret existente (mesma linha), nunca
    cria uma segunda.

    O `secret` é criptografado em repouso (Fernet) porque, diferente
    da chave pública do WebAuthn, ele é simétrico: quem possui o
    secret consegue gerar códigos válidos. Nunca é exposto em nenhuma
    resposta HTTP depois de confirmado -- ver to_dict().

    `confirmado=False` até o usuário provar, no cadastro, que
    escaneou/configurou certo e consegue gerar um código válido.
    """

    __tablename__ = "credencial_totp"

    id_credencial = db.Column(db.BigInteger, primary_key=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, unique=True, index=True
    )

    # Secret em base32, criptografado com Fernet antes de persistir.
    # Nome de coluna "secret" no banco; exposto na classe só via
    # secret_plano (getter) e definir_secret (setter), nunca direto.
    _secret_criptografado = db.Column("secret", db.String(255), nullable=False)

    confirmado = db.Column(db.Boolean, nullable=False, default=False)

    criado_em = db.Column(db.DateTime, server_default=db.func.now())

    @property
    def secret_plano(self) -> str:
        """Descriptografa o secret para uso em tempo de verificação
        (pyotp.TOTP(secret_plano).verify(codigo)). Nunca logar nem
        incluir em nenhuma resposta HTTP.
        """
        return _fernet.decrypt(self._secret_criptografado.encode()).decode()

    def definir_secret(self, secret_plano: str) -> None:
        """Criptografa e grava um novo secret -- usado tanto no
        cadastro inicial quanto numa reconfiguração (substituindo o
        anterior).
        """
        self._secret_criptografado = _fernet.encrypt(secret_plano.encode()).decode()

    def to_dict(self):
        """
        Retorna um dicionário formatado para a tela de configurações.
        Nunca inclui o secret, nem criptografado.
        """
        data_formatada = self.criado_em.strftime("%d/%m/%Y") if self.criado_em else ""

        return {
            "id_credencial": self.id_credencial,
            "confirmado": self.confirmado,
            "criado_em": data_formatada,
        }