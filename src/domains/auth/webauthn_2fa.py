"""
webauthn_2fa.py

WebAuthn como segundo fator de autenticação. Cobre dois assuntos: confirmar
uma sessão que ficou pendente depois do login por senha ou por Google, e
gerenciar as credenciais (dispositivos) do usuário: listar, cadastrar e
remover.

A confirmação do login trabalha em cima de `mfa_pendente` e `id_usuario` na
sessão, sem depender de como a sessão chegou a esse estado. O cadastro de
dispositivo precisa funcionar tanto para quem já tem sessão completa
(configurações da conta) quanto para quem está no onboarding escolhendo o
primeiro método de 2FA. A remoção só bloqueia apagar a última credencial se o
usuário também não tiver um TOTP confirmado, já que o login sempre exige 2FA.

Limite de tentativas: cada pedido de desafio de login conta como uma tentativa
nova, não importa por que a anterior falhou (sem autenticador, PIN errado,
timeout, cancelamento). O contador vive na sessão, então zera a cada novo
login e não é persistido por usuário. Ao atingir o máximo, novos desafios são
recusados e cabe ao frontend tentar TOTP como próximo método, se o usuário
tiver. Se TOTP também não estiver disponível ou esgotar, não sobra caminho de
login: o 2FA é sempre obrigatório e não há fallback para Google sem 2FA.
"""

import base64
import json

from flask import Blueprint, request, jsonify, session
from webauthn import (
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
    generate_registration_options,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
    AuthenticatorSelectionCriteria,
)

from src.models import db
from src.models.usuarios.credencial_totp import CredencialTOTP
from src.models.usuarios.credencial_webauthn import CredencialWebAuthn
from src.core.session import (
    mfa_pendente_required,
    get_id_usuario_sessao,
    requer_login,
    get_usuario_sessao,
    requer_login_ou_onboarding_pendente,
)
from src.domains.auth.webauthn_config import RP_ID, EXPECTED_ORIGIN, RP_NAME
from src.domains.auth.onboarding import cadastro_de_fator_permitido, marcar_fator_comprovado

bp_webauthn_2fa = Blueprint("webauthn_2fa", __name__)

MAX_TENTATIVAS_MFA = 3


def descritores_credenciais(credenciais) -> list:
    """Converte credenciais salvas em descritores WebAuthn (usados em allow/exclude credentials)."""
    return [
        PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
        for c in credenciais
    ]


def _credenciais_como_dict(id_usuario) -> list:
    """Lista as credenciais do usuário já no formato de saída da API (`to_dict()`)."""
    credenciais = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).all()
    return [c.to_dict() for c in credenciais]


def carregar_configuracoes() -> list:
    """Credenciais WebAuthn do usuário da sessão, no formato de saída da API."""
    return _credenciais_como_dict(get_id_usuario_sessao())


def _resposta_opcoes_com_tentativas(opcoes, tentativas_usadas):
    """Serializa as opções WebAuthn e anexa `tentativas_restantes`.

    `options_to_json` devolve uma string JSON no formato que o
    `@simplewebauthn/browser` espera (`challenge` e `allowCredentials` em
    base64url). O parse é feito só para injetar um campo extra na raiz:
    `tentativas_restantes` não faz parte do schema WebAuthn e é ignorado pela
    biblioteca do navegador; existe só para o frontend decidir a UI (mostrar
    "última tentativa", oferecer o próximo método).
    """
    corpo = json.loads(options_to_json(opcoes))
    corpo["tentativas_restantes"] = max(0, MAX_TENTATIVAS_MFA - tentativas_usadas)
    return jsonify(corpo), 200


class Webauthn():

    # ------------------------------------------------------------------
    # Gerenciamento de credenciais (sessão completa ou onboarding)
    # ------------------------------------------------------------------

    @staticmethod
    @bp_webauthn_2fa.get("/configuracoes")
    @requer_login
    def configuracoes():
        """Lista os dispositivos WebAuthn cadastrados pelo usuário logado.

        Retorno:
            200 com {"webauthn": [...]}.
        """
        return jsonify({"webauthn": carregar_configuracoes()})

    @staticmethod
    @bp_webauthn_2fa.post("/registrar/iniciar")
    @requer_login_ou_onboarding_pendente
    def registrar_dispositivo_iniciar():
        """Gera o desafio WebAuthn para cadastrar um NOVO dispositivo.

        Diferente de `/2fa/iniciar` (que autentica uma credencial existente
        para confirmar um login pendente), esta rota gera um desafio de
        REGISTRO. Aceita sessão completa ou em onboarding_pendente.
        `exclude_credentials` evita cadastrar o mesmo autenticador físico duas
        vezes para o mesmo usuário.

        Retorno:
            200 com as opções de registro em JSON.
            403 se o cadastro de fator não for permitido no onboarding (ver
                `cadastro_de_fator_permitido` em onboarding.py).
        """
        usuario = get_usuario_sessao()

        if not cadastro_de_fator_permitido(usuario):
            return jsonify({"erro": "cadastro_de_fator_nao_permitido"}), 403

        credenciais_existentes = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).all()

        opcoes = generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=str(usuario.id).encode(),
            user_name=usuario.email,
            user_display_name=usuario.nome_completo,
            exclude_credentials=descritores_credenciais(credenciais_existentes),
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )

        session["registro_webauthn_challenge"] = base64.b64encode(opcoes.challenge).decode()

        return options_to_json(opcoes), 200, {"Content-Type": "application/json"}

    @staticmethod
    @bp_webauthn_2fa.post("/registrar/confirmar")
    @requer_login_ou_onboarding_pendente
    def registrar_dispositivo_confirmar():
        """Valida a resposta de registro e persiste a nova credencial.

        Aceita sessão completa ou em onboarding_pendente.

        Corpo esperado (JSON):
            {
              "apelido": "Notebook do trabalho",
              "tipo": "mobile" | "usb" | "desktop",   (padrão "desktop")
              "credencial": { ...resposta de startRegistration()... }
            }

        Retorno:
            201 com a lista atualizada de credenciais (`webauthn.credenciais`).
            400 se faltar apelido ou credencial, ou a verificação falhar.
            403 se o cadastro de fator não for permitido no onboarding.
            409 se a credencial (mesmo credential_id) já estiver cadastrada.
        """
        usuario = get_usuario_sessao()

        if not cadastro_de_fator_permitido(usuario):
            return jsonify({"erro": "cadastro_de_fator_nao_permitido"}), 403

        corpo = request.get_json() or {}
        resposta_credencial = corpo.get("credencial")
        apelido = (corpo.get("apelido") or "").strip()
        tipo = corpo.get("tipo") or "desktop"

        if not resposta_credencial:
            return jsonify({"erro": "credencial_ausente"}), 400
        if not apelido:
            return jsonify({"erro": "apelido_obrigatorio"}), 400

        challenge_esperado = base64.b64decode(session.get("registro_webauthn_challenge", ""))

        try:
            verificacao = verify_registration_response(
                credential=resposta_credencial,
                expected_challenge=challenge_esperado,
                expected_rp_id=RP_ID,
                expected_origin=EXPECTED_ORIGIN,
            )
        except Exception as erro:
            return jsonify({"erro": "registro_invalido", "detalhe": str(erro)}), 400

        credential_id = base64.urlsafe_b64encode(verificacao.credential_id).decode().rstrip("=")

        if CredencialWebAuthn.query.filter_by(credential_id=credential_id).first():
            return jsonify({"erro": "credencial_ja_cadastrada"}), 409

        # Os campos do model são apelido_dispositivo e tipo_dispositivo; "apelido"
        # e "tipo" só existem na saída de to_dict(), que traduz para o formato do front.
        db.session.add(CredencialWebAuthn(
            id_usuario=usuario.id,
            credential_id=credential_id,
            public_key=verificacao.credential_public_key,
            sign_count=verificacao.sign_count,
            apelido_dispositivo=apelido,
            tipo_dispositivo=tipo,
        ))
        db.session.commit()

        marcar_fator_comprovado()
        session.pop("registro_webauthn_challenge", None)

        return jsonify({"webauthn": {"credenciais": _credenciais_como_dict(usuario.id)}}), 201

    @staticmethod
    @bp_webauthn_2fa.delete("/credenciais/<int:id_credencial>")
    @requer_login
    def remover_credencial(id_credencial):
        """Remove um dispositivo (credencial WebAuthn) do usuário logado.

        Remover a última credencial só é bloqueado se o usuário também não
        tiver um TOTP confirmado: sem nenhum fator, ele ficaria sem 2FA, o que
        não é permitido. Havendo TOTP confirmado, a última (ou única)
        credencial WebAuthn pode ser removida livremente.

        Retorno:
            200 com a lista atualizada de credenciais.
            404 se a credencial não existir ou não pertencer ao usuário logado.
            409 se for a última credencial E o usuário não tiver TOTP
                confirmado como alternativa.
        """
        usuario = get_usuario_sessao()

        credencial = CredencialWebAuthn.query.filter_by(
            id_credencial=id_credencial, id_usuario=usuario.id
        ).first()

        if not credencial:
            return jsonify({"erro": "credencial_nao_encontrada"}), 404

        total_credenciais = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).count()
        if total_credenciais <= 1:
            tem_totp = CredencialTOTP.query.filter_by(
                id_usuario=usuario.id, confirmado=True
            ).first() is not None
            if not tem_totp:
                return jsonify({"erro": "ultima_credencial_nao_pode_ser_removida"}), 409

        db.session.delete(credencial)
        db.session.commit()

        return jsonify({"webauthn": {"credenciais": _credenciais_como_dict(usuario.id)}}), 200

    # ------------------------------------------------------------------
    # Segundo fator no login (sessão em mfa_pendente)
    # ------------------------------------------------------------------

    @staticmethod
    @bp_webauthn_2fa.post("/2fa/iniciar")
    @mfa_pendente_required
    def segundo_fator_iniciar():
        """Gera o desafio WebAuthn para confirmar o segundo fator do login.

        `user_verification=REQUIRED` obriga o autenticador a confirmar a
        identidade localmente (PIN ou biometria); só presença física não basta.
        Sem isso, alguém com o notebook desbloqueado, mas sem o PIN, ainda
        passaria pelo 2FA em certos autenticadores.

        Cada chamada consome uma tentativa (`mfa_tentativas` na sessão), até
        `MAX_TENTATIVAS_MFA`. O contador só avança depois de as opções serem
        geradas com sucesso, para uma falha interna não consumir a tentativa
        do usuário.

        Retorno:
            200 com as opções de autenticação em JSON e `tentativas_restantes`.
            400 com `sem_credencial_cadastrada` se o usuário não tiver
                credencial; o frontend deve seguir direto para TOTP.
            429 com `limite_tentativas_excedido` se o limite já foi atingido.
        """
        id_usuario = get_id_usuario_sessao()

        tentativas = session.get("mfa_tentativas", 0)
        if tentativas >= MAX_TENTATIVAS_MFA:
            return jsonify({
                "erro": "limite_tentativas_excedido",
                "tentativas_restantes": 0,
            }), 429

        credenciais = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).all()
        if not credenciais:
            return jsonify({"erro": "sem_credencial_cadastrada"}), 400

        opcoes = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=descritores_credenciais(credenciais),
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        session["mfa_webauthn_challenge"] = base64.b64encode(opcoes.challenge).decode()

        tentativas += 1
        session["mfa_tentativas"] = tentativas

        return _resposta_opcoes_com_tentativas(opcoes, tentativas)

    @staticmethod
    @bp_webauthn_2fa.post("/2fa/confirmar")
    @mfa_pendente_required
    def segundo_fator_confirmar():
        """Valida a assinatura WebAuthn e promove a sessão a completa.

        A liberação da sessão é centralizada em
        `AuthService.liberar_sessao_completa`, a mesma chamada por
        totp_2fa.py, para as duas confirmações não divergirem.

        Corpo esperado (JSON): resposta de autenticação do WebAuthn.

        Retorno:
            200 com `id_usuario`, `email` e `id_empresa` se a assinatura for válida.
            401 se a credencial não for encontrada ou a assinatura for inválida,
                ou `sessao_invalida` se o usuário foi desativado nesse meio-tempo.
        """
        id_usuario = get_id_usuario_sessao()
        challenge_esperado = base64.b64decode(session.get("mfa_webauthn_challenge", ""))
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
                expected_origin=EXPECTED_ORIGIN,
                credential_public_key=credencial.public_key,
                credential_current_sign_count=credencial.sign_count,
            )
        except Exception as erro:
            return jsonify({"erro": "assinatura_invalida", "detalhe": str(erro)}), 401

        credencial.sign_count = verificacao.new_sign_count
        db.session.commit()

        from src.domains.usuario.repository import UsuarioRepository
        from src.domains.auth.services import AuthService
        usuario = UsuarioRepository().find_by_id(id_usuario)

        if not AuthService().liberar_sessao_completa(usuario, db):
            return jsonify({"erro": "sessao_invalida"}), 401

        return jsonify({
            "id_usuario": usuario.id,
            "email": usuario.email,
            "id_empresa": usuario.id_empresa,
        }), 200