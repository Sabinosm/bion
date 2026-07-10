"""Rota informativa de status de sessão.

Diferente de `/auth/me`, esta rota não bloqueia -- apenas informa em
que estado a sessão está. Usada pela página pós-login logo após o
redirect do Google, para decidir se o usuário deve ir para onboarding,
confirmação de 2FA, ou dashboard. Mantém o contrato de resposta somente
em JSON, mesmo sendo uma rota de apoio à navegação.
"""

from flask import Blueprint, session, jsonify

bp_status = Blueprint("status", __name__)


@bp_status.route("/status", methods=["GET"])
def status_sessao():
    """Retorna o estado atual da sessão sem exigir autenticação completa.

    Retorno:
        200 com `status: autenticado`, `onboarding_requerido` ou
        `mfa_requerido`, conforme o estado da sessão.
        401 com `status: nao_autenticado` se não houver sessão iniciada.
    """
    if not session.get("usuario_id") and not session.get("id_usuario"):
        return jsonify({"status": "nao_autenticado"}), 401

    if session.get("onboarding_pendente"):
        return jsonify({"status": "onboarding_requerido"}), 200

    if session.get("mfa_pendente"):
        return jsonify({"status": "mfa_requerido", "metodo": "webauthn"}), 200

    return jsonify({"status": "autenticado"}), 200