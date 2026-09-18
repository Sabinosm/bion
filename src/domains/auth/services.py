"""Serviço de autenticação por login e senha."""

from argon2.exceptions import VerifyMismatchError
from src.core.security import ph
from src.domains.usuario.repository import UsuarioRepository
from src.models.usuarios import Usuario
from src.core.session import session


class AuthService:
    """Serviço responsável por validar credenciais de login/senha."""

    def __init__(self):
        self.repo = UsuarioRepository()

    def autenticar(self, login: str, senha: str):
        """Autentica um usuário por login e senha.

        Também aplica rehash automático da senha caso os parâmetros do
        algoritmo Argon2id tenham evoluído desde o último hash salvo.

        Parâmetros:
            login: login informado pelo usuário.
            senha: senha em texto plano informada pelo usuário.

        Retorno:
            Tupla (Usuario, None) se as credenciais forem válidas.
            Tupla (None, "sem_senha") se o usuário só possuir login via Google.
            Tupla (None, None) se as credenciais forem inválidas ou o
            usuário não existir/estiver inativo.
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
        """Promove a sessão pendente (mfa_pendente) a sessão completa,
        após o segundo fator ter sido confirmado. Compartilhado por
        webauthn_2fa.py e totp_2fa.py para não duplicar essa lógica
        entre os dois módulos.
        """
        usuario.status = "ativo"
        db.session.commit()
        session.pop("mfa_pendente", None)
        session.pop("mfa_webauthn_challenge", None)
        session.pop("mfa_tentativas", None)
        session.pop("totp_tentativas", None)
        session["id_empresa"] = usuario.id_empresa
        session["is_super_admin"] = usuario.is_super_admin
