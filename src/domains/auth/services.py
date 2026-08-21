"""Serviço de autenticação por login e senha."""

from argon2.exceptions import VerifyMismatchError
from flask import jsonify
from src.core.exceptions import BionException
from src.core.security import ph
from src.domains.usuario.repository import UsuarioRepository
from src.models.usuarios import Usuario



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
    
    def load(self, usuario: Usuario):
        """Carrega o usuário da sessão atual."""
        from src.domains.configuracao.service import ConfiguracaoService
        from src.core.session import get_id_usuario_sessao
        from flask import session
        
        
        session["id_empresa"] = usuario.id_empresa
        cfg_service = ConfiguracaoService()
        cfg = cfg_service.obter_ou_criar(get_id_usuario_sessao())
        
        data = {"usuario": usuario.to_dict(), "configuracoes": cfg.to_dict()}
            
        return data
    
        