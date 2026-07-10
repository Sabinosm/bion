# auth/onboarding.py
#
# Rotas exclusivas do primeiro acesso, chamadas depois do login via Google
# quando usuario.onboarding_pendente == True.
#
# Fluxo: 1) define senha  2) cadastra WebAuthn  3) sessão completa liberada
#
# O cadastro do WebAuthn em si (registro_iniciar/registro_concluir) é o
# MESMO código do arquivo auth_webauthn.py já criado — só o decorator muda,
# de @login_required para @onboarding_pendente_required.

import base64
from flask import Blueprint, request, jsonify, session
from argon2 import PasswordHasher

from src.models import db
from src.models.usuarios import Usuario, CredencialWebAuthn 
from src.core.session import onboarding_pendente_required
from src.core.validacoes import validar_senha

from src.domains.auth.webauthn_2fa import generate_registration_options, verify_registration_response, options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
)

bp_onboarding = Blueprint("onboarding", __name__)
ph = PasswordHasher()

RP_ID = "bion.com.br"
RP_NAME = "Bion"




@bp_onboarding.route("/onboarding/definir-senha", methods=["POST"])
@onboarding_pendente_required
def definir_senha():
    dados = request.get_json()
    nova_senha = dados.get("senha")

    senha_valida, resposta = validar_senha(nova_senha)
    
    if senha_valida == False:
        return jsonify(resposta),400
    
    usuario = Usuario.query.get(session["id_usuario"])
    usuario.hash_senha = ph.hash(nova_senha)
    db.session.commit()

    return jsonify({"status": "senha_definida", "proximo_passo": "cadastrar_webauthn"}), 200


@bp_onboarding.route("/onboarding/webauthn/iniciar", methods=["POST"])
@onboarding_pendente_required
def onboarding_webauthn_iniciar():
    usuario = Usuario.query.get(session["id_usuario"])

    if not usuario.hash_senha:
        # Força a ordem: senha antes de WebAuthn
        return jsonify({"erro": "defina_senha_primeiro"}), 400

    opcoes = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(usuario.id).encode(),
        user_name=usuario.email,
        user_display_name=usuario.nome or usuario.email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # authenticator_attachment NÃO especificado (fica None):
            # permite tanto Face ID/Windows Hello local quanto o celular
            # como autenticador remoto via QR code (cross-device/passkey).
            # Especificar PLATFORM aqui travaria só no dispositivo do cadastro.
            user_verification=UserVerificationRequirement.PREFERRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
    )

    session["webauthn_challenge"] = base64.b64encode(opcoes.challenge).decode()

    return options_to_json(opcoes), 200, {"Content-Type": "application/json"}


@bp_onboarding.route("/onboarding/webauthn/concluir", methods=["POST"])
@onboarding_pendente_required
def onboarding_webauthn_concluir():
    id_usuario = session["id_usuario"]
    challenge_esperado = base64.b64decode(session.get("webauthn_challenge", ""))
    resposta_credencial = request.get_json()

    try:
        verificacao = verify_registration_response(
            credential=resposta_credencial,
            expected_challenge=challenge_esperado,
            expected_rp_id=RP_ID,
            expected_origin="https://bion.com.br", # Alterar
        )
    except Exception as erro:
        return jsonify({"erro": "credencial_invalida", "detalhe": str(erro)}), 400

    nova_credencial = CredencialWebAuthn(
        id_usuario=id_usuario,
        credential_id=base64.urlsafe_b64encode(verificacao.credential_id).decode(),
        public_key=verificacao.credential_public_key,
        sign_count=verificacao.sign_count,
        apelido_dispositivo=resposta_credencial.get("apelido", "Dispositivo principal"),
    )
    db.session.add(nova_credencial)

    # ONBOARDING CONCLUÍDO: libera a sessão completa
    usuario = Usuario.query.get(id_usuario)
    usuario.onboarding_pendente = False
    db.session.commit()

    session.pop("onboarding_pendente", None)
    session.pop("webauthn_challenge", None)
    session["id_empresa"] = usuario.id_empresa

    return jsonify({
        "status": "onboarding_concluido",
        "id_usuario": usuario.id,
        "id_empresa": usuario.id_empresa,
    }), 200