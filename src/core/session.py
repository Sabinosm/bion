"""
Gestão de Cookies e Sessão do Bion (API JSON-only).

CORREÇÃO MANTIDA: no bion.zip original, o controller de login gravava
`session["usuario_uuid"]`, mas estas funções liam `session.get("usuario_id")`.
A sessão nunca era reconhecida como autenticada e `requer_login` sempre
falhava mesmo após login bem-sucedido. Padronizado em `usuario_id`
(chave primária interna, busca mais barata que por uuid); o controller de
auth grava `session["usuario_id"] = usuario.id` no login.

Diferença em relação à versão web: os decorators agora retornam respostas
JSON (401/403) em vez de redirect + flash, já que não há mais páginas HTML
para redirecionar o usuário.
"""

from functools import wraps
from flask import session, jsonify


def _usuario_sessao():
    """Retorna o Usuario logado ou None."""
    uid = session.get("usuario_id")
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
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            return _nao_autenticado()
        return f(*args, **kwargs)
    return decorated


def requer_medico(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            return _nao_autenticado()
        if session.get("tipo_usuario") != "medico":
            return _sem_permissao("médicos")
        return f(*args, **kwargs)
    return decorated


def requer_enfermeiro(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            return _nao_autenticado()
        if session.get("tipo_usuario") != "enfermeiro":
            return _sem_permissao("enfermeiros")
        return f(*args, **kwargs)
    return decorated


def requer_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            return _nao_autenticado()
        if session.get("tipo_usuario") != "admin":
            return _sem_permissao("administradores")
        return f(*args, **kwargs)
    return decorated


def requer_medico_ou_enfermeiro(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            return _nao_autenticado()
        if session.get("tipo_usuario") not in ("medico", "enfermeiro"):
            return _sem_permissao("profissionais de saúde")
        return f(*args, **kwargs)
    return decorated
