# auth/step_up.py
#
# Step-up authentication: reconfirma a identidade via WebAuthn antes de
# ações perigosas (excluir prontuário, alterar prescrição, dar acesso
# admin), mesmo com a sessão já totalmente autenticada.
#
# Mecanismo: gera um token de curta duração, vinculado ao id_usuario e à
# ação específica, guardado na tabela stepup_token (ver src/database/stepup.py).
# A rota perigosa exige esse token. 

import base64
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, session

from src.database import db
from src.database.usuarios import CredencialWebAuthn
from src.database.step_up import StepUpToken
from src.core.session import requer_login

from webauthn import generate_authentication_options, verify_authentication_response, options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

bp_step_up = Blueprint("step_up", __name__)

RP_ID = "bion.com.br"
DURACAO_TOKEN_SEGUNDOS = 180  # 3 minutos, curto de propósito


@bp_step_up.route("/stepup/iniciar", methods=["POST"])
@requer_login
def stepup_iniciar():
    """
    Chamado pelo frontend quando uma rota perigosa responde 403
    'confirmacao_requerida'. Gera o desafio WebAuthn de novo.
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
        user_verification=UserVerificationRequirement.REQUIRED,  # mais rígido aqui
    )

    session["stepup_challenge"] = base64.b64encode(opcoes.challenge).decode()

    return options_to_json(opcoes), 200, {"Content-Type": "application/json"}


@bp_step_up.route("/stepup/confirmar", methods=["POST"])
@requer_login
def stepup_confirmar():
    """
    Valida a assinatura WebAuthn e emite um token de confirmação de
    curta duração, vinculado à AÇÃO específica que o frontend informa
    (ex: 'excluir_prontuario'). O token não serve para outra ação.
    """
    id_usuario = session["id_usuario"]
    dados = request.get_json()
    acao = dados.get("acao")

    if not acao:
        return jsonify({"erro": "acao_nao_especificada"}), 400

    challenge_esperado = base64.b64decode(session.get("stepup_challenge", ""))
    resposta_credencial = dados.get("credencial")

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
    session.pop("stepup_challenge", None)

    # Gera um token de uso único, curto, vinculado a essa ação específica.
    # Remove qualquer token antigo da mesma (usuario, acao) antes de criar
    # o novo, pra não acumular linhas velhas caso o usuário chame de novo
    # sem confirmar a anterior.
    StepUpToken.query.filter_by(id_usuario=id_usuario, acao=acao).delete()

    token = secrets.token_urlsafe(32)
    db.session.add(StepUpToken(
        id_usuario=id_usuario,
        acao=acao,
        token=token,
        expira_em=datetime.now(timezone.utc) + timedelta(seconds=DURACAO_TOKEN_SEGUNDOS),
    ))
    db.session.commit()

    return jsonify({
        "token_confirmacao": token,
        "acao": acao,
        "expira_em_segundos": DURACAO_TOKEN_SEGUNDOS,
    }), 200


def requer_confirmacao_recente(acao):
    """
    Decorator para rotas perigosas. Uso:

        @app.route("/prontuarios/<id>", methods=["DELETE"])
        @requer_login
        @requer_confirmacao_recente("excluir_prontuario")
        def excluir_prontuario(id):
            ...

    O frontend deve mandar o token no header X-Stepup-Token.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            id_usuario = session.get("id_usuario")
            token_recebido = request.headers.get("X-Stepup-Token")

            if not token_recebido:
                return jsonify({"erro": "confirmacao_requerida", "acao": acao}), 403

            registro = StepUpToken.query.filter_by(
                id_usuario=id_usuario, acao=acao, token=token_recebido
            ).first()

            if not registro or registro.expirado():
                return jsonify({"erro": "confirmacao_requerida", "acao": acao}), 403

            # Uso único: apaga o token assim que validado, mesmo que a
            # ação falhe depois por outro motivo — evita reuso do token
            db.session.delete(registro)
            db.session.commit()

            return f(*args, **kwargs)
        return wrapper
    return decorator