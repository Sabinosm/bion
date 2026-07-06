# auth/status.py
#
# Rota puramente informativa: diz em que estado a sessão está, sem
# bloquear como o /auth/me faz. Usada pela página pos-login.html logo
# depois do redirect do Google, para decidir se manda o usuário para
# onboarding.html, confirmar-2fa.html, ou dashboard.html.
#
# Mantém o contrato "Bion só responde JSON" — mesmo essa rota de apoio
# à navegação devolve JSON, nunca HTML.

from flask import Blueprint, session, jsonify

bp_status = Blueprint("status", __name__)


@bp_status.route("/status", methods=["GET"])
def status_sessao():
    if not session.get("usuario_id") and not session.get("id_usuario"):
        return jsonify({"status": "nao_autenticado"}), 401

    if session.get("onboarding_pendente"):
        return jsonify({"status": "onboarding_requerido"}), 200

    if session.get("mfa_pendente"):
        return jsonify({"status": "mfa_requerido", "metodo": "webauthn"}), 200

    return jsonify({"status": "autenticado"}), 200