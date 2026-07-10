"""WebAuthn como segundo fator de autenticação.

Diferente de um WebAuthn usado como login primário, aqui ele apenas
confirma uma sessão que já está pendente após o login por senha ou
Google. As rotas de registro do dispositivo seguem o mesmo mecanismo;
somente as rotas de confirmação de login mudam de comportamento.
"""

import base64
from flask import Blueprint, request, jsonify, session
from webauthn import (
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
    generate_registration_options,
    verify_registration_response,
)
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from src.models import db
from src.models.usuarios import Usuario, CredencialWebAuthn
from src.core.session import mfa_pendente_required

bp_webauthn_2fa = Blueprint("webauthn_2fa", __name__)

RP_ID = "bion.com.br"


@bp_webauthn_2fa.route("/webauthn/2fa/iniciar", methods=["POST"])
@mfa_pendente_required
def segundo_fator_iniciar():
    """Gera o desafio WebAuthn para confirmar o segundo fator.

    Chamado após o login por senha/Google, quando a sessão está pendente
    de confirmação (`mfa_pendente=True`).

    Retorno:
        200 com as opções de autenticação em JSON.
        400 se o usuário não tiver nenhuma credencial cadastrada (não
        deveria ocorrer se o login já checou a existência de 2FA).
    """
    id_usuario = session["id_usuario"]

    credenciais = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).all()
    if not credenciais:
        return jsonify({"erro": "sem_credencial_cadastrada"}), 400

    permitir = [
        PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
        for c in credenciais
    ]

    opcoes = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=permitir,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    session["webauthn_challenge"] = base64.b64encode(opcoes.challenge).decode()

    return options_to_json(opcoes), 200, {"Content-Type": "application/json"}


@bp_webauthn_2fa.route("/webauthn/2fa/confirmar", methods=["POST"])
@mfa_pendente_required
def segundo_fator_confirmar():
    """Valida a assinatura WebAuthn e promove a sessão a completa.

    Corpo esperado (JSON): resposta de autenticação do WebAuthn.

    Retorno:
        200 com os dados de usuário/empresa se a assinatura for válida.
        401 se a credencial não for encontrada ou a assinatura for inválida.
    """
    id_usuario = session["id_usuario"]
    challenge_esperado = base64.b64decode(session.get("webauthn_challenge", ""))
    resposta_credencial = request.get_json()

    credencial = CredencialWebAuthn.query.filter_by(
        credential_id=resposta_credencial["id"]
    ).first()

    if not credencial or credencial.id_usuario != id_usuario:
        return jsonify({"erro": "credencial_nao_encontrada"}), 401

    try:
        verificacao = verify_authentication_response(
            credential=resposta_credencial,
            expected_challenge=challenge_esperado,
            expected_rp_id=RP_ID,
            expected_origin="https://bion.com.br",
            credential_public_key=credencial.public_key,
            credential_current_sign_count=credencial.sign_count,
        )
    except Exception as erro:
        return jsonify({"erro": "assinatura_invalida", "detalhe": str(erro)}), 401

    credencial.sign_count = verificacao.new_sign_count
    db.session.commit()

    usuario = Usuario.query.get(id_usuario)

    session.pop("mfa_pendente", None)
    session.pop("webauthn_challenge", None)
    session["id_empresa"] = usuario.id_empresa

    return jsonify({
        "id_usuario": usuario.id,
        "email": usuario.email,
        "id_empresa": usuario.id_empresa,
    }), 200