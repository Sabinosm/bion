"""
services.py

Serviço de autenticação por login e senha. Valida as credenciais com Argon2id,
atualizando o hash automaticamente quando os parâmetros do algoritmo evoluem,
e promove uma sessão pendente de segundo fator a sessão completa. Essa
promoção é compartilhada pelos módulos de WebAuthn e de TOTP para que a
lógica não seja duplicada entre eles.
"""

from typing import Optional, Tuple

from argon2.exceptions import VerifyMismatchError

from src.core.security import ph
from src.domains.usuario.repository import UsuarioRepository
from src.models.usuarios import Usuario
from src.core.session import session


class AuthService:
    """Valida credenciais de login/senha e libera a sessão após o 2FA."""

    def __init__(self):
        self.repo = UsuarioRepository()

    def autenticar(self, login: str, senha: str) -> Tuple[Optional[Usuario], Optional[str]]:
        """Autentica um usuário por login e senha.

        Se o hash salvo estiver desatualizado em relação aos parâmetros atuais
        do Argon2id, regrava a senha com o hash novo.

        Args:
            login: login informado pelo usuário.
            senha: senha em texto plano informada pelo usuário.

        Returns:
            (Usuario, None) se as credenciais forem válidas.
            (None, "sem_senha") se o usuário existe e está ativo, mas só tem
                login via Google.
            (None, None) se as credenciais forem inválidas ou o usuário não
                existir ou estiver inativo.
        """
        usuario = self.repo.find_by_login(login)
        if not usuario or usuario.status == "inativo":
            return None, None

        if usuario.hash_senha is None:
            return None, "sem_senha"

        try:
            ph.verify(usuario.hash_senha, senha)
        except VerifyMismatchError:
            return None, None

        if ph.check_needs_rehash(usuario.hash_senha):
            usuario.hash_senha = ph.hash(senha)
            self.repo.save(usuario)

        return usuario, None

    def liberar_sessao_completa(self, usuario: Usuario, db):
        """Promove a sessão pendente de 2FA a sessão completa.

        Chamado depois que o segundo fator foi confirmado: marca o usuário como
        ativo, descarta os estados temporários do 2FA (flag pendente, desafio e
        contadores de tentativa) e grava `id_empresa`, o sinal de que a
        autenticação terminou.

        Args:
            usuario: usuário que acabou de confirmar o segundo fator.
            db: instância do SQLAlchemy usada para o commit.
        """
        usuario.status = "ativo"
        db.session.commit()
        session.pop("mfa_pendente", None)
        session.pop("mfa_webauthn_challenge", None)
        session.pop("mfa_tentativas", None)
        session.pop("totp_tentativas", None)
        session["id_empresa"] = usuario.id_empresa
        session["is_super_admin"] = usuario.is_super_admin