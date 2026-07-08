"""
Rotas de login/logout (le e escreve a sessao via cookie httpOnly).

Alem disso, o `return f"<{usuario.uuid}>"` do controller original (que
devolvia uma string solta, nao JSON) foi substituido por uma resposta
JSON padronizada, ja que a API agora e JSON-only.

2FA (WebAuthn) ADICIONADO: apos autenticar login/senha, se o usuario
tiver credencial WebAuthn cadastrada, a sessao fica em estado
PENDENTE (mfa_pendente=True) e id_empresa NAO e liberado ainda. Only
depois da confirmacao via /webauthn/2fa/confirmar (ver webauthn_2fa.py)
a sessao e promovida a completa.
"""

from flask import Blueprint, request, session, jsonify
from src.database.usuarios import Usuario, CredencialWebAuthn
from src.core.responses import json_success, json_error
from src.domains.configuracao.service import ConfiguracaoService
from .services import AuthService


bp = Blueprint("auth", __name__)
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

    tem_2fa = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).first() is not None

    session.clear()
    session.permanent = True                    # respeita PERMANENT_SESSION_LIFETIME
    session["id_usuario"] = usuario.id           # chave lida por todos os decorators
    session["tipo_usuario"] = usuario.tipo_usuario
    session["uuid_usuario"] = usuario.uuid       # conveniência para o front-end
    session["id_empresa"] = usuario.id_empresa

    if tem_2fa:
        # Sessão FICA PENDENTE — id_empresa não é liberado ainda.
        # Decorators de acesso (requer_login) devem tratar essa flag
        # como "não autenticado" até a confirmação via WebAuthn.
        session["mfa_pendente"] = True
        return json_success(
            data={"status": "mfa_requerido", "metodo": "webauthn"},
            message="Confirmação adicional necessária.",
        )

    # Sem 2FA cadastrado: libera a sessão completa normalmente
    session["id_empresa"] = usuario.id_empresa

    cfg_service = ConfiguracaoService()
    cfg = cfg_service.obter_ou_criar(session["id_usuario"])

    return json_success(
        data={"usuario": usuario.to_dict(), "configuracoes": cfg.to_dict()},
        message="Login realizado com sucesso.",
    )


@bp.get("/me")
def me():
    if not session.get("id_usuario"):
        return json_error("Nenhuma sessão ativa.", 401)

    if session.get("mfa_pendente"):
        return json_error("Confirmação de segundo fator pendente.", 401)

    from src.domains.usuario.repository import UsuarioRepository
    usuario = UsuarioRepository().find_by_id(session["id_usuario"])
    if not usuario:
        session.clear()
        return json_error("Sessão inválida.", 401)
    return json_success(data={"usuario": usuario.to_dict()})


@bp.post("/logout")
def logout():
    session.clear()
    return json_success(message="Sessão encerrada.")
