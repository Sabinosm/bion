"""
Rotas de login/logout (le e escreve a sessao via cookie httpOnly).

CORRECAO APLICADA (bug ja identificado e corrigido em src/core/session.py):
o controller original gravava `session["usuario_uuid"]` no login, mas
todo o resto do app (decorators requer_login etc.) lia
`session.get("usuario_id")`. A sessao nunca era reconhecida como
autenticada. Aqui o login grava tanto `usuario_id` (uso interno dos
decorators) quanto `tipo_usuario` (uso dos decorators de papel) na
sessao, e devolve o uuid do usuario no corpo JSON para o front-end.

Alem disso, o `return f"<{usuario.uuid}>"` do controller original (que
devolvia uma string solta, nao JSON) foi substituido por uma resposta
JSON padronizada, ja que a API agora e JSON-only.
"""

from flask import Blueprint, request, session, jsonify

from src.core.responses import json_success, json_error
from .services import AuthService

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
_svc = AuthService()


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or request.form.to_dict()
    login_val = (data.get("login") or "").strip()
    senha = data.get("senha") or ""

    if not login_val or not senha:
        return json_error("Login e senha são obrigatórios.", 422)

    usuario = _svc.autenticar(login_val, senha)
    if not usuario:
        return json_error("Login ou senha incorretos.", 401)

    session.permanent = True                    # respeita PERMANENT_SESSION_LIFETIME
    session["usuario_id"] = usuario.id           # chave lida por todos os decorators
    session["tipo_usuario"] = usuario.tipo_usuario
    session["usuario_uuid"] = usuario.uuid       # conveniência para o front-end

    return json_success(
        data={"usuario": usuario.to_dict()},
        message="Login realizado com sucesso.",
    )


@bp.get("/me")
def me():
    if not session.get("usuario_id"):
        return json_error("Nenhuma sessão ativa.", 401)
    from src.domains.usuario.repository import UsuarioRepository
    usuario = UsuarioRepository().find_by_id(session["usuario_id"])
    if not usuario:
        session.clear()
        return json_error("Sessão inválida.", 401)
    return json_success(data={"usuario": usuario.to_dict()})


@bp.post("/logout")
def logout():
    session.clear()
    return json_success(message="Sessão encerrada.")
