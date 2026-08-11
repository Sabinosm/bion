"""Rota informativa de status de sessão.

Diferente de `/auth/me`, esta rota não bloqueia -- apenas informa em
que estado a sessão está. Usada pela página pós-login logo após o
redirect do Google, para decidir se o usuário deve ir para onboarding,
confirmação de 2FA, ou dashboard. Mantém o contrato de resposta somente
em JSON, mesmo sendo uma rota de apoio à navegação.
"""

from flask import Blueprint, session, jsonify, g
from src.core.responses import json_error, json_success
from src.core.session import requer_login

bp_status = Blueprint("status", __name__)


@bp_status.route("/status", methods=["GET"])
def status_sessao():
    from src.models.usuarios import Usuario
    """Retorna o estado atual da sessão sem exigir autenticação completa.

    Retorno:
        200 com `status: autenticado`, `onboarding_pendente` (incluindo
        `senha_definida: bool` para o frontend saber se pode pular a
        etapa de senha) ou `mfa_pendente`.
        401 com `status: nao_autenticado` se não houver sessão iniciada.
    """
    if not session.get("id_usuario"):
        return jsonify({"status": "nao_autenticado"}), 401

    if session.get("onboarding_pendente"):
        usuario = Usuario.query.get(session["id_usuario"])
        return jsonify({
            "status": "onboarding_pendente",
            "senha_definida": usuario.hash_senha is not None,
        }), 200

    if session.get("mfa_pendente"):
        return jsonify({"status": "mfa_pendente", "metodo": "webauthn"}), 200

    return jsonify({"status": "completa"}), 200

@bp_status.get("/me")
@requer_login
def me():
    """Retorna os dados do usuário autenticado na sessão atual.

    Retorno:
        200 com os dados do usuário.
        401 se a sessão referenciar um usuário que não existe mais
        (nesse caso a sessão também é limpa).
    """
    from src.domains.usuario.repository import UsuarioRepository
    usuario = UsuarioRepository().find_by_id(g.id_usuario)
    if not usuario:
        session.clear()
        return json_error("Sessão inválida.", 401)
    return json_success(data={"usuario": usuario.to_dict()})


@bp_status.get("/check-session")
def ck_session():
    from src.core.session import ja_logado
    """Verifica se já existe uma sessão ativa

    
        Retorno:
            200 Se já existe
            401 Se não existe
            
        """
    return ja_logado()