"""
Gestão de Cookies e Sessão do Bion (API JSON-only).

CORREÇÃO MANTIDA: no bion.zip original, o controller de login gravava
`session["usuario_uuid"]`, mas estas funções liam `session.get("id_usuario")`.
A sessão nunca era reconhecida como autenticada e `requer_login` sempre
falhava mesmo após login bem-sucedido. Padronizado em `id_usuario`
(chave primária interna, busca mais barata que por uuid); o controller de
auth grava `session["id_usuario"] = usuario.id` no login.

Diferença em relação à versão web: os decorators agora retornam respostas
JSON (401/403) em vez de redirect + flash, já que não há mais páginas HTML
para redirecionar o usuário.
"""

from functools import wraps
from flask import session, jsonify


def _usuario_sessao():
    """Retorna o Usuario logado ou None."""
    uid = session.get("id_usuario")
    if not uid:
        return None
    from src.domains.usuario.repository import UsuarioRepository
    return UsuarioRepository().find_by_id(uid)


def get_usuario_sessao():
    return _usuario_sessao()


def _nao_autenticado():
    return jsonify({"status": "error", "message": "Autenticação necessária."}), 401


def _sem_permissao(papel):
    return jsonify({"status": "error", "message": f"Acesso restrito a {papel}."}), 403


def requer_login(f):
    """
    Bloqueia qualquer rota clínica/normal a menos que a sessão esteja
    TOTALMENTE liberada: sem onboarding pendente e sem 2FA pendente.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario"):
            return jsonify({"erro": "nao_autenticado"}), 401
 
        if session.get("onboarding_pendente"):
            return jsonify({"erro": "onboarding_requerido"}), 403
 
        if session.get("mfa_pendente"):
            return jsonify({"erro": "mfa_requerido"}), 401
 
        return f(*args, **kwargs)
    return wrapper
 
 
def onboarding_pendente_required(f):
    """Usado só nas rotas de onboarding (definir senha, cadastrar WebAuthn)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("onboarding_pendente"):
            return jsonify({"erro": "sessao_invalida"}), 401
        return f(*args, **kwargs)
    return wrapper
 
 
def mfa_pendente_required(f):
    """Usado só nas rotas do segundo fator (login recorrente)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("mfa_pendente"):
            return jsonify({"erro": "sessao_invalida"}), 401
        return f(*args, **kwargs)
    return wrapper


def requer_medico(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("id_usuario"):
            return _nao_autenticado()
        if session.get("tipo_usuario") != "medico":
            return _sem_permissao("médicos")
        return f(*args, **kwargs)
    return decorated


def requer_enfermeiro(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("id_usuario"):
            return _nao_autenticado()
        if session.get("tipo_usuario") != "enfermeiro":
            return _sem_permissao("enfermeiros")
        return f(*args, **kwargs)
    return decorated


def requer_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("id_usuario"):
            return _nao_autenticado()
        if session.get("tipo_usuario") != "admin":
            return _sem_permissao("administradores")
        return f(*args, **kwargs)
    return decorated


def requer_medico_ou_enfermeiro(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("id_usuario"):
            return _nao_autenticado()
        if session.get("tipo_usuario") not in ("medico", "enfermeiro"):
            return _sem_permissao("profissionais de saúde")
        return f(*args, **kwargs)
    return decorated
