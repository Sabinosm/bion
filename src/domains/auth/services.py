"""
Servico de autenticacao.

Mantido praticamente identico ao original (app/auth/service.py):
verifica a senha com Argon2id e faz rehash automatico se os parametros
do algoritmo tiverem evoluido desde o ultimo hash salvo.
"""

from argon2.exceptions import VerifyMismatchError

from src.core.security import ph
from src.domains.usuario.repository import UsuarioRepository


class AuthService:

    def __init__(self):
        self.repo = UsuarioRepository()

    def autenticar(self, login: str, senha: str):
        """Retorna Usuario se credenciais validas, None caso contrario."""
        usuario = self.repo.find_by_login(login)
        if not usuario or usuario.status != "ativo":
            return None
        try:
            ph.verify(usuario.hash_senha, senha)
            if ph.check_needs_rehash(usuario.hash_senha):
                usuario.hash_senha = ph.hash(senha)
                self.repo.save(usuario)
            return usuario
        except VerifyMismatchError:
            return None
