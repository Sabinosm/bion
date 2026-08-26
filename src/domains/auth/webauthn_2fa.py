"""WebAuthn como segundo fator de autenticação.

Diferente de um WebAuthn usado como login primário, aqui ele apenas
confirma uma sessão que já está pendente após o login por senha. As
rotas de registro do dispositivo seguem o mesmo mecanismo; somente as
rotas de confirmação de login mudam de comportamento.

Login via Google não passa por aqui
-------------------------------------
Login via Google (oauth.py) nunca entra em `mfa_pendente`, mesmo que
o usuário tenha uma credencial WebAuthn cadastrada -- autenticar com
sucesso via Google já é considerado prova de identidade suficiente.
As rotas deste módulo só são acionadas depois de um login por senha
(login.py) para um usuário que já tem WebAuthn cadastrado.

Limite de tentativas
---------------------
Cada chamada a `/webauthn/2fa/iniciar` conta como uma tentativa nova
(um desafio distinto gerado do zero) -- não importa por que a
tentativa anterior falhou (sem autenticador, PIN errado, timeout,
cancelamento). O contador vive na sessão (`mfa_tentativas`), então
zera a cada novo login -- não é persistido por usuário.

Ao atingir `MAX_TENTATIVAS_MFA`, `/webauthn/2fa/iniciar` para de
gerar novos desafios e devolve `limite_tentativas_excedido`. Cabe ao
frontend, nesse caso, redirecionar de volta para a tela de login --
o usuário pode então reautenticar por senha (nova tentativa de 2FA,
contador reiniciado) ou por Google (que não exige 2FA).
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
from src.core.session import mfa_pendente_required, get_id_usuario_sessao, requer_login, get_usuario_sessao
from src.domains.auth.webauthn_config import RP_ID, EXPECTED_ORIGIN

bp_webauthn_2fa = Blueprint("webauthn_2fa", __name__)

MAX_TENTATIVAS_MFA = 3


def _resposta_opcoes_com_tentativas(opcoes, tentativas_usadas):
    """Serializa as opções WebAuthn e anexa `tentativas_restantes`.

    `options_to_json` devolve uma string JSON pronta para o formato
    que `@simplewebauthn/browser` espera (campos como `challenge` e
    `allowCredentials` em base64url). Fazemos parse dela só para
    injetar um campo extra no nível raiz -- `tentativas_restantes` não
    faz parte do schema WebAuthn, então @simplewebauthn simplesmente
    ignora esse campo ao consumir a resposta; ele existe só para o
    frontend decidir a UI (mostrar "última tentativa", oferecer o
    fallback direto, etc.).
    """
    import json

    corpo = json.loads(options_to_json(opcoes))
    corpo["tentativas_restantes"] = max(0, MAX_TENTATIVAS_MFA - tentativas_usadas)
    return jsonify(corpo), 200

def carregar_configuracoes():
        id_usuario = get_id_usuario_sessao()
        credenciais = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).all()
        
        # Retorna uma lista do Python (com itens ou vazia)
        return [c.to_dict() for c in credenciais] if credenciais else []

class Webauthn():
    
    
    @staticmethod
    @bp_webauthn_2fa.get("/configuracoes")
    @requer_login
    def configuracoes():
        # Pega apenas a lista limpa
        lista_webauthn = carregar_configuracoes()
        
        # Agora sim você monta o JSON final perfeitamente
        return jsonify({"webauthn":lista_webauthn})
        

    @staticmethod
    @bp_webauthn_2fa.post("/2fa/iniciar")
    @mfa_pendente_required
    def segundo_fator_iniciar():
        """Gera o desafio WebAuthn para confirmar o segundo fator.

        Chamado após o login por senha/Google, quando a sessão está pendente
        de confirmação (`mfa_pendente=True`).

        `user_verification=REQUIRED` obriga o autenticador a confirmar a
        identidade localmente (PIN ou biometria) -- não basta só presença
        física (ex.: encostar o dedo sem ler a digital). Sem isso, alguém
        com o notebook desbloqueado mas sem saber o PIN/senha do SO ainda
        conseguiria passar pelo 2FA em certos autenticadores.

        Cada chamada aqui consome uma tentativa (`mfa_tentativas` na
        sessão), até `MAX_TENTATIVAS_MFA`. Isso limita quantos desafios
        distintos o frontend pode pedir nesta sessão antes de precisar
        redirecionar o usuário de volta ao login -- ver módulo docstring.

        Retorno:
            200 com as opções de autenticação em JSON e `tentativas_restantes`.
            400 se o usuário não tiver nenhuma credencial cadastrada (não
            deveria ocorrer se o login já checou a existência de 2FA).
            429 se o limite de tentativas já tiver sido atingido.
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

        permitir = [
            PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
            for c in credenciais
        ]

        opcoes = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=permitir,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        session["mfa_webauthn_challenge"] = base64.b64encode(opcoes.challenge).decode()

        # Incrementa só depois de gerar as opções com sucesso -- uma
        # falha interna aqui (ex.: erro ao consultar credenciais) não deve
        # consumir a tentativa do usuário.
        tentativas += 1
        session["mfa_tentativas"] = tentativas

        return _resposta_opcoes_com_tentativas(opcoes, tentativas)


    @staticmethod
    @bp_webauthn_2fa.post("/2fa/confirmar")
    @mfa_pendente_required
    def segundo_fator_confirmar():
        """Valida a assinatura WebAuthn e promove a sessão a completa.

        Corpo esperado (JSON): resposta de autenticação do WebAuthn.

        Retorno:
            200 com os dados de usuário/empresa se a assinatura for válida.
            401 se a credencial não for encontrada ou a assinatura for inválida.
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

        usuario = get_id_usuario_sessao

        session.pop("mfa_pendente", None)
        session.pop("mfa_webauthn_challenge", None)
        session.pop("mfa_tentativas", None)
        session["id_empresa"] = usuario.id_empresa

        return jsonify({
            "id_usuario": usuario.id,
            "email": usuario.email,
            "id_empresa": usuario.id_empresa,
        }), 200
        

    