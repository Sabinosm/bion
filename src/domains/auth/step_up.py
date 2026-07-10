"""Step-up authentication.

Reconfirma a identidade via WebAuthn antes de ações sensíveis (excluir
prontuário, alterar prescrição, conceder acesso admin), mesmo com a
sessão já totalmente autenticada.

Mecanismo: gera um token de curta duração vinculado ao `id_usuario` e à
ação específica, guardado na tabela `stepup_token`. A rota sensível
exige esse token via decorator `requer_confirmacao_recente`.
"""

import base64
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, session

from src.models import db
from src.models.usuarios import CredencialWebAuthn
from src.models.auditoria import StepUpToken
from src.core.session import requer_login

from webauthn import generate_authentication_options, verify_authentication_response, options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

bp_step_up = Blueprint("step_up", __name__)

RP_ID = "bion.com.br"
DURACAO_TOKEN_SEGUNDOS = 180


@bp_step_up.route("/stepup/iniciar", methods=["POST"])
@requer_login
def stepup_iniciar():
    """Gera um novo desafio WebAuthn para reconfirmação de identidade.

    Chamado pelo frontend quando uma rota sensível responde 403 com
    `confirmacao_requerida`.

    Retorno:
        200 com as opções de autenticação em JSON.
        400 se o usuário não tiver nenhuma credencial cadastrada.
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
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    session["stepup_challenge"] = base64.b64encode(opcoes.challenge).decode()

    return options_to_json(opcoes), 200, {"Content-Type": "application/json"}


@bp_step_up.route("/stepup/confirmar", methods=["POST"])
@requer_login
def stepup_confirmar():
    """Valida a assinatura WebAuthn e emite um token de confirmação.

    O token é de uso único, curto e vinculado à ação específica
    informada pelo frontend (ex.: `excluir_prontuario`) -- não serve
    para confirmar nenhuma outra ação. Qualquer token anterior da mesma
    combinação (usuário, ação) é removido antes de emitir o novo.

    Corpo esperado (JSON): `acao` e `credencial` (resposta WebAuthn).

    Retorno:
        200 com o token de confirmação e seu tempo de expiração.
        400 se a ação não for especificada.
        401 se a credencial não for encontrada ou a assinatura for inválida.
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
    """Decorator que exige um token de step-up recente para a rota.

    O frontend deve enviar o token no header `X-Stepup-Token`. O token
    é consumido (apagado) assim que validado, mesmo que a ação decorada
    falhe depois por outro motivo -- evitando reuso.

    Uso:
        @app.route("/prontuarios/<id>", methods=["DELETE"])
        @requer_login
        @requer_confirmacao_recente("excluir_prontuario")
        def excluir_prontuario(id):
            ...

    Parâmetros:
        acao: identificador da ação sensível protegida.

    Retorno:
        Decorator que envolve a view protegida, retornando 403 com
        `confirmacao_requerida` caso o token esteja ausente, incorreto
        ou expirado.
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

            db.session.delete(registro)
            db.session.commit()

            return f(*args, **kwargs)
        return wrapper
    return decorator