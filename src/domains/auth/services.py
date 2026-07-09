"""
Servico de autenticacao.

Mantido praticamente identico ao original (app/auth/service.py):
verifica a senha com Argon2id e faz rehash automatico se os parametros
do algoritmo tiverem evoluido desde o ultimo hash salvo.
"""

from argon2.exceptions import VerifyMismatchError
from flask import jsonify
from src.core.security import ph
from src.domains.usuario.repository import UsuarioRepository


class AuthService:

    def __init__(self):
        self.repo = UsuarioRepository()

    def autenticar(self, login: str, senha: str):
        """Retorna (Usuario, None) se credenciais validas.
        Retorna (None, 'sem_senha') se o usuário só tem login via Google.
        Retorna (None, None) se credenciais invalidas."""
        usuario = self.repo.find_by_login(login)
        if not usuario or usuario.status != "ativo":
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
