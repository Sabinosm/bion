"""WebAuthn como segundo fator de autenticação.

Diferente de um WebAuthn usado como login primário, aqui ele apenas
confirma uma sessão que já está pendente após o login por senha. As
rotas de registro do dispositivo seguem o mesmo mecanismo; somente as
rotas de confirmação de login mudam de comportamento.

ALTERADO (2FA sempre obrigatório, também via Google)
-------------------------------------------------------
A seção "Login via Google não passa por aqui" (versão anterior deste
módulo) não é mais verdadeira -- ver oauth.py. Login via Google agora
também entra em `mfa_pendente=True` e usa as MESMAS rotas de
confirmação deste módulo (`/2fa/iniciar`, `/2fa/confirmar`) e de
totp_2fa.py. Nenhuma rota aqui precisou mudar por causa disso -- elas
já trabalhavam em cima de `mfa_pendente`/`id_usuario` na sessão, sem
depender de como a sessão chegou nesse estado (senha ou Google).

ALTERADO (2FA sempre obrigatório -- registro durante onboarding)
----------------------------------------------------------------------
`registrar_dispositivo_iniciar`/`confirmar` agora usam
`requer_login_ou_onboarding_pendente` em vez de `requer_login` --
precisam funcionar tanto para quem já está com sessão completa
(configurações da conta) quanto para quem está no meio do onboarding
escolhendo o primeiro método de 2FA (ver onboarding.py). Ver
session.py para o novo decorator.

ALTERADO (remoção da última credencial -- agora considera TOTP)
----------------------------------------------------------------------
`remover_credencial` bloqueava remover a última CredencialWebAuthn
partindo do princípio de que WebAuthn era o único 2FA existente. Isso
não é mais verdade (ver totp_2fa.py) -- agora o bloqueio só se aplica
se o usuário NÃO tiver também um TOTP confirmado. Ver comentário na
própria função.

Limite de tentativas
---------------------
Cada chamada a `/webauthn/2fa/iniciar` conta como uma tentativa nova
(um desafio distinto gerado do zero) -- não importa por que a
tentativa anterior falhou (sem autenticador, PIN errado, timeout,
cancelamento). O contador vive na sessão (`mfa_tentativas`), então
zera a cada novo login -- não é persistido por usuário.

Ao atingir `MAX_TENTATIVAS_MFA`, `/webauthn/2fa/iniciar` para de
gerar novos desafios e devolve `limite_tentativas_excedido`. ALTERADO:
diferente da versão anterior, isso não significa mais "volte ao login
e use Google" -- cabe ao frontend tentar TOTP como próximo método, se
o usuário tiver (ver totp_2fa.py e afterLogin.js). Só se TOTP também
não estiver disponível ou esgotar é que não sobra mais nenhum caminho
de login (ver mfa.py, login.py, oauth.py -- 2FA é sempre obrigatório,
não há mais fallback para Google sem 2FA).

CORRIGIDO (bug pré-existente, sem relação com múltiplos admins):
`segundo_fator_confirmar` fazia `usuario = get_id_usuario_sessao`
(sem parênteses -- pegava a referência da função, não chamava nem
buscava o Usuario) e depois lia `usuario.id_empresa`/`usuario.id`,
que quebraria em runtime (função não tem esses atributos). Corrigido
para buscar o Usuario de verdade via UsuarioRepository.

ALTERADO (múltiplos admins por empresa):
- `session["is_super_admin"]` é reforçado aqui na confirmação do 2FA,
  já que a sessão é reconstruída neste ponto (mesmo padrão de
  `session["id_empresa"]` logo abaixo). Na prática já teria sido
  gravado em login.py antes deste fluxo começar, mas repetir aqui
  evita depender dessa ordem implícita entre arquivos.
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
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
    AuthenticatorSelectionCriteria,
)

from src.models import db
from src.models.usuarios import Usuario, CredencialWebAuthn, CredencialTOTP
from src.core.session import (
    mfa_pendente_required,
    get_id_usuario_sessao,
    requer_login,
    get_usuario_sessao,
    requer_login_ou_onboarding_pendente,
)
from src.domains.auth.webauthn_config import RP_ID, EXPECTED_ORIGIN, RP_NAME

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
    @bp_webauthn_2fa.post("/registrar/iniciar")
    @requer_login_ou_onboarding_pendente
    def registrar_dispositivo_iniciar():
        """Gera o desafio WebAuthn para cadastrar um NOVO dispositivo.

        Diferente de `/2fa/iniciar` (que autentica uma credencial já
        existente para confirmar um login pendente), esta rota gera um
        desafio de REGISTRO.

        ALTERADO (2FA sempre obrigatório): antes exigia sessão já
        completa (`@requer_login`) -- agora também aceita sessão em
        onboarding_pendente, já que o onboarding passou a exigir
        escolher WebAuthn ou TOTP antes de concluir (ver onboarding.py
        e session.py::requer_login_ou_onboarding_pendente).

        `exclude_credentials` evita que o mesmo autenticador físico seja
        cadastrado duas vezes para o mesmo usuário.

        Retorno:
            200 com as opções de registro em JSON.
        """
        usuario = get_usuario_sessao()

        credenciais_existentes = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).all()
        excluir = [
            PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
            for c in credenciais_existentes
        ]

        opcoes = generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=str(usuario.id).encode(),
            user_name=usuario.email,
            user_display_name=usuario.nome_completo,
            exclude_credentials=excluir,
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

        ALTERADO (2FA sempre obrigatório): mesmo motivo de
        registrar_dispositivo_iniciar -- aceita também sessão em
        onboarding_pendente.

        Corpo esperado (JSON):
            {
              "apelido": "Notebook do trabalho",
              "tipo": "mobile" | "usb" | "desktop",
              "credencial": { ...resposta de startRegistration()... }
            }

        Retorno:
            201 com a lista atualizada de credenciais (`webauthn.credenciais`).
            400 se faltar apelido/credencial ou a verificação falhar.
            409 se a credencial (mesmo credential_id) já estiver cadastrada.
        """
        usuario = get_usuario_sessao()
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

        ja_existe = CredencialWebAuthn.query.filter_by(credential_id=credential_id).first()
        if ja_existe:
            return jsonify({"erro": "credencial_ja_cadastrada"}), 409

        # Campos confirmados em credencial_webauthn.py: apelido_dispositivo
        # e tipo_dispositivo (não "apelido"/"tipo" -- esses só existem na
        # saída de to_dict(), que já traduz os nomes pro formato do front).
        nova = CredencialWebAuthn(
            id_usuario=usuario.id,
            credential_id=credential_id,
            public_key=verificacao.credential_public_key,
            sign_count=verificacao.sign_count,
            apelido_dispositivo=apelido,
            tipo_dispositivo=tipo,
        )
        db.session.add(nova)
        db.session.commit()

        session.pop("registro_webauthn_challenge", None)

        lista_atual = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).all()
        return jsonify({"webauthn": {"credenciais": [c.to_dict() for c in lista_atual]}}), 201

    @staticmethod
    @bp_webauthn_2fa.delete("/credenciais/<int:id_credencial>")
    @requer_login
    def remover_credencial(id_credencial):
        """Remove um dispositivo (credencial WebAuthn) do usuário logado.

        Delete simples de linha -- CredencialWebAuthn não tem
        relacionamentos dependentes, então não existe "delete completo"
        de nada além da própria linha.

        ALTERADO (bloqueio agora considera TOTP também): antes, a
        ÚLTIMA credencial WebAuthn nunca podia ser removida, partindo
        do princípio de que WebAuthn era o único 2FA existente no
        sistema. Com TOTP também disponível (ver totp_2fa.py), isso
        mudou: remover a última credencial WebAuthn só é bloqueado se
        o usuário TAMBÉM não tiver um TOTP confirmado -- do contrário,
        ele ficaria sem 2FA algum, o que não é mais permitido (login
        sempre exige 2FA, ver login.py/oauth.py). Se o usuário tiver
        TOTP confirmado, pode remover a última (ou única) credencial
        WebAuthn livremente -- o TOTP sozinho já mantém a conta em
        conformidade com a exigência de 2FA.

        Retorno:
            200 com a lista atualizada de credenciais.
            403 se a credencial não pertencer ao usuário logado (mesma
                resposta de 404, para não vazar se o id existe ou não).
            409 se for a última credencial do usuário E ele não tiver
                TOTP confirmado como alternativa.
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

        lista_atual = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).all()
        return jsonify({"webauthn": {"credenciais": [c.to_dict() for c in lista_atual]}}), 200

    @staticmethod
    @bp_webauthn_2fa.post("/2fa/iniciar")
    @mfa_pendente_required
    def segundo_fator_iniciar():
        """Gera o desafio WebAuthn para confirmar o segundo fator.

        Chamado após o login por senha OU por Google (ALTERADO: Google
        também entra em mfa_pendente agora, ver oauth.py), quando a
        sessão está pendente de confirmação.

        `user_verification=REQUIRED` obriga o autenticador a confirmar a
        identidade localmente (PIN ou biometria) -- não basta só presença
        física (ex.: encostar o dedo sem ler a digital). Sem isso, alguém
        com o notebook desbloqueado mas sem saber o PIN/senha do SO ainda
        conseguiria passar pelo 2FA em certos autenticadores.

        Cada chamada aqui consome uma tentativa (`mfa_tentativas` na
        sessão), até `MAX_TENTATIVAS_MFA`. Isso limita quantos desafios
        distintos o frontend pode pedir nesta sessão antes de precisar
        tentar o próximo método (TOTP, se o usuário tiver -- ver
        docstring do módulo e totp_2fa.py).

        Retorno:
            200 com as opções de autenticação em JSON e `tentativas_restantes`.
            400 se o usuário não tiver nenhuma credencial cadastrada --
            nesse caso o frontend deve pular direto para TOTP.
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

        # CORRIGIDO: era `usuario = get_id_usuario_sessao` (referência da
        # função, sem chamar) -- usuario.id_empresa/.id quebrariam em
        # runtime. Busca o Usuario de verdade.
        from src.domains.usuario.repository import UsuarioRepository
        usuario = UsuarioRepository().find_by_id(id_usuario)

        session.pop("mfa_pendente", None)
        session.pop("mfa_webauthn_challenge", None)
        session.pop("mfa_tentativas", None)
        session["id_empresa"] = usuario.id_empresa
        # ADICIONADO: reforça o dado já gravado em login.py -- ver
        # docstring do módulo.
        session["is_super_admin"] = usuario.is_super_admin

        return jsonify({
            "id_usuario": usuario.id,
            "email": usuario.email,
            "id_empresa": usuario.id_empresa,
        }), 200