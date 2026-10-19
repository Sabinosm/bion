"""
step_up.py

Step-up authentication: reconfirma a identidade antes de ações sensíveis
(excluir prontuário, alterar prescrição, conceder acesso admin), mesmo com a
sessão já totalmente autenticada. O resultado de qualquer método é um token de
curta duração, vinculado ao usuário e à ação e guardado em tabela, que a rota
sensível exige por meio do decorator de confirmação recente. O decorator não
precisa saber qual método foi usado para obtê-lo.

Métodos, na ordem em que são tentados:

1. WebAuthn, se o usuário tiver credencial cadastrada. Gera um desafio
   vinculado ao usuário e à ação.
2. TOTP, se o usuário não tiver WebAuthn, ou se o frontend o escolher depois
   de uma falha do WebAuthn (as rotas ficam em totp_2fa.py). Também vinculado
   à ação.
3. Senha mais Google (fallback), liberado pelo servidor só em dois casos: o
   usuário não tem nenhum fator, ou tem TOTP e esgotou as tentativas dele no
   step-up da ação. O WebAuthn não tem contador de tentativas, então quem só
   tem WebAuthn não tem fallback. Acontece em duas etapas: primeiro confirma a
   senha atual, depois reautentica no Google com `prompt=login`, que força o
   Google a pedir login de novo mesmo com sessão ativa no navegador (sem isso
   seria só um SSO silencioso, que não prova nada novo). O estado entre as
   etapas fica em tabela, e não na sessão Flask, porque o fluxo atravessa um
   redirect real de navegador e pode voltar em outra aba. No retorno, o
   e-mail do Google precisa ser o do usuário e estar verificado e, se o
   usuário já tiver `google_sub` vinculado, o `sub` precisa ser o mesmo.

Por que o step-up mantém uma saída, diferente do login: no login, perder os
dois fatores é bloqueio total, pois não sobra caminho de entrada. No step-up a
pessoa já está dentro do sistema, e negar toda forma de confirmar uma ação
seria mais rígido que o necessário para quem não tem fator ou esgotou o TOTP.
O fallback é deliberadamente mais fraco que WebAuthn e TOTP, pois senha mais
Google prova a posse de duas credenciais que já autenticaram a sessão
original, e não de algo além dela.

A checagem do token também existe como função nomeada, e não só dentro do
decorator, porque o controller de usuário precisa dela de forma condicional:
só quando o payload mexe em campos sensíveis (is_admin, tipo de papel), e não
na rota inteira.
"""

import base64
import json
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, session, redirect, url_for

from argon2.exceptions import VerifyMismatchError
from webauthn import generate_authentication_options, verify_authentication_response, options_to_json
from webauthn.helpers.structs import UserVerificationRequirement

from src.models import db
from src.models.usuarios import CredencialWebAuthn
from src.models.auditoria.stepup import StepUpToken
from src.models.auditoria.stepup_reautenticacao import StepUpReautenticacao
from src.core.security import ph
from src.core.session import requer_login, get_usuario_sessao, get_id_usuario_sessao
from src.domains.auth.mfa import metodo_stepup, metodos_2fa_disponiveis
from src.domains.auth.webauthn_config import RP_ID, EXPECTED_ORIGIN
from src.domains.auth.frontend_config import FRONTEND_URL
from src.domains.auth.oauth import oauth, google_confere_usuario
from src.domains.auth.totp_2fa import MAX_TENTATIVAS_TOTP, resetar_tentativas_stepup_totp
from src.domains.auth.webauthn_2fa import descritores_credenciais
from src.domains.usuario.repository import UsuarioRepository

bp_step_up = Blueprint("step_up", __name__)

DURACAO_TOKEN_SEGUNDOS = 180
DURACAO_REAUTENTICACAO_SEGUNDOS = 300

# Ponto de entrada estático no frontend para onde o callback de reautenticação
# redireciona ao terminar. Mesmo padrão de oauth.py: o backend só conhece esse
# arquivo, nunca a estrutura interna de pastas do frontend.
CAMINHO_APOS_REAUTENTICACAO = "/html/pages/auth/stepup_callback.html"


def _emitir_token(id_usuario, acao) -> str:
    """Emite um StepUpToken novo para (usuário, ação), apagando o anterior da mesma combinação.

    Compartilhado por todos os métodos de confirmação (WebAuthn, TOTP e
    senha mais Google).

    Returns:
        O token gerado.
    """
    StepUpToken.query.filter_by(id_usuario=id_usuario, acao=acao).delete()

    token = secrets.token_urlsafe(32)
    db.session.add(StepUpToken(
        id_usuario=id_usuario,
        acao=acao,
        token=token,
        expira_em=datetime.now(timezone.utc) + timedelta(seconds=DURACAO_TOKEN_SEGUNDOS),
    ))
    db.session.commit()

    return token


def token_recente_valido(acao: str) -> bool:
    """Verifica e CONSOME um token de step-up recente para `acao`, lido do header X-Stepup-Token.

    Pode ser chamada pelo decorator (rota inteira sensível) ou de forma
    condicional dentro de uma view que só é sensível dependendo do payload.

    O token é de uso único: um token válido e não expirado é apagado assim que
    aceito, para não permitir reuso, mesmo que a ação protegida falhe depois.
    Token ausente, incorreto ou expirado não é consumido.

    Returns:
        True se havia um token válido e ele já foi consumido. False caso
        contrário; quem chama decide o que fazer (normalmente, 403 com
        `confirmacao_requerida`).
    """
    id_usuario = get_id_usuario_sessao()
    token_recebido = request.headers.get("X-Stepup-Token")

    if not token_recebido:
        return False

    registro = StepUpToken.query.filter_by(
        id_usuario=id_usuario, acao=acao, token=token_recebido
    ).first()

    if not registro or registro.expirado():
        return False

    db.session.delete(registro)
    db.session.commit()
    return True


def _redirecionar_frontend(querystring: str):
    """Redireciona para o ponto de entrada do frontend pós-reautenticação, com a querystring dada."""
    return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_REAUTENTICACAO}?{querystring}")


def _falhar_reautenticacao(pendente, erro: str):
    """Descarta o registro de reautenticação pendente (se houver) e redireciona com o código de erro."""
    if pendente:
        db.session.delete(pendente)
    db.session.commit()
    return _redirecionar_frontend(f"erro={erro}")


def _fallback_senha_google_liberado(id_usuario, acao) -> bool:
    """Informa se o fallback senha + Google está liberado para a `acao`.

    Liberado se o usuário não tem nenhum fator, ou se tem TOTP e esgotou as
    tentativas do step-up desta ação. Quem só tem WebAuthn não tem fallback,
    porque o WebAuthn não tem contador de tentativas.
    """
    metodos = metodos_2fa_disponiveis(id_usuario)
    if not metodos:
        return True
    if "totp" not in metodos:
        return False
    return (
        session.get("stepup_totp_acao") == acao
        and session.get("stepup_totp_tentativas", 0) >= MAX_TENTATIVAS_TOTP
    )


class StepUp():

    @staticmethod
    @bp_step_up.route("/iniciar", methods=["POST"])
    @requer_login
    def stepup_iniciar():
        """Inicia a reconfirmação de identidade, no método disponível para o usuário.

        Chamado pelo frontend quando uma rota sensível responde 403 com
        `confirmacao_requerida`.

        A `acao` é exigida já aqui, e não só na confirmação, e fica vinculada
        ao desafio gerado: assim não dá para iniciar um step-up para uma ação e
        confirmar outra. O método vem de `metodo_stepup` (mfa.py), a mesma
        ordem de preferência do login, resolvendo conta sem fator para o
        fallback "senha_google".

        Corpo esperado (JSON): `acao`.

        Retorno:
            200 com `metodo: "webauthn"` e as opções de autenticação, se o
                usuário tiver credencial WebAuthn.
            200 com `metodo: "totp"`, `acao` e `tentativas_restantes`, se não
                tiver WebAuthn mas tiver TOTP confirmado. O reset de
                tentativas já é feito aqui, então o frontend não precisa
                chamar `/totp/2fa/stepup/iniciar` de novo; só usa essa rota
                para reiniciar o TOTP depois de uma falha do WebAuthn.
            200 com `metodo: "senha_google"` e `acao`, se não tiver nenhum
                dos dois; o frontend segue para `/stepup/senha/confirmar`.
            400 se `acao` não for informada.
        """
        id_usuario = get_id_usuario_sessao()

        dados = request.get_json(silent=True) or {}
        acao = dados.get("acao")
        if not acao:
            return jsonify({"erro": "acao_nao_especificada"}), 400

        metodo = metodo_stepup(id_usuario)

        if metodo == "totp":
            return jsonify({
                "metodo": "totp",
                "acao": acao,
                "tentativas_restantes": resetar_tentativas_stepup_totp(acao),
            }), 200

        if metodo == "senha_google":
            return jsonify({"metodo": "senha_google", "acao": acao}), 200

        # Daqui para baixo só resta "webauthn".
        credenciais = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).all()

        opcoes = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=descritores_credenciais(credenciais),
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        session["stepup_challenge"] = {
            "challenge": base64.b64encode(opcoes.challenge).decode(),
            "acao": acao,
        }

        corpo = {"metodo": "webauthn"}
        corpo.update(json.loads(options_to_json(opcoes)))
        return jsonify(corpo), 200

    @staticmethod
    @bp_step_up.route("/confirmar", methods=["POST"])
    @requer_login
    def stepup_confirmar():
        """Valida a assinatura WebAuthn do step-up e emite um token de confirmação.

        Exige que a `acao` enviada seja a mesma vinculada ao desafio gerado em
        `/iniciar`.

        Corpo esperado (JSON): `acao` e `credencial` (resposta de autenticação
        do WebAuthn).

        Retorno:
            200 com `token_confirmacao`, `acao` e `expira_em_segundos`.
            400 se faltar `acao` ou se não houver desafio iniciado.
            401 se a ação não corresponder ao desafio, a credencial não for
                encontrada ou a assinatura for inválida.
        """
        id_usuario = get_id_usuario_sessao()
        dados = request.get_json()
        acao = dados.get("acao")

        if not acao:
            return jsonify({"erro": "acao_nao_especificada"}), 400

        pendente = session.get("stepup_challenge")
        if not pendente:
            return jsonify({"erro": "desafio_nao_iniciado"}), 400

        if acao != pendente.get("acao"):
            return jsonify({"erro": "acao_nao_corresponde_ao_desafio"}), 401

        challenge_esperado = base64.b64decode(pendente["challenge"])
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
                expected_origin=EXPECTED_ORIGIN,
                credential_public_key=credencial.public_key,
                credential_current_sign_count=credencial.sign_count,
            )
        except Exception as erro:
            return jsonify({"erro": "assinatura_invalida", "detalhe": str(erro)}), 401

        credencial.sign_count = verificacao.new_sign_count
        session.pop("stepup_challenge", None)
        db.session.commit()

        token = _emitir_token(id_usuario, acao)

        return jsonify({
            "token_confirmacao": token,
            "acao": acao,
            "expira_em_segundos": DURACAO_TOKEN_SEGUNDOS,
        }), 200

    @staticmethod
    @bp_step_up.route("/senha/confirmar", methods=["POST"])
    @requer_login
    def stepup_senha_confirmar():
        """Primeira etapa do fallback: confirma a senha atual e devolve a URL de reautenticação no Google.

        Só é liberado para usuário sem nenhum fator ou com TOTP e tentativas
        esgotadas no step-up desta ação (ver `_fallback_senha_google_liberado`).

        Cria um registro `StepUpReautenticacao` (usuário, ação, `state` e
        `nonce` de correlação, expira em `DURACAO_REAUTENTICACAO_SEGUNDOS`),
        substituindo qualquer pendência anterior da mesma combinação, e monta a
        URL de autorização do Google com `prompt=login`.

        Corpo esperado (JSON): `acao` e `senha`.

        Retorno:
            200 com {"redirect_url": "..."} para o frontend redirecionar o navegador.
            400 se faltar `acao` ou `senha`, ou se o usuário não tiver senha definida.
            401 se a senha estiver incorreta.
            403 se o fallback não estiver liberado: só vale para usuário sem
                fator ou com TOTP e tentativas esgotadas.
        """
        id_usuario = get_id_usuario_sessao()
        dados = request.get_json(silent=True) or {}
        acao = dados.get("acao")
        senha = dados.get("senha")

        if not acao or not senha:
            return jsonify({"erro": "dados_incompletos"}), 400

        if not _fallback_senha_google_liberado(id_usuario, acao):
            return jsonify({"erro": "fallback_indisponivel"}), 403

        usuario = get_usuario_sessao()

        if not usuario or not usuario.hash_senha:
            return jsonify({"erro": "senha_nao_definida"}), 400

        try:
            ph.verify(usuario.hash_senha, senha)
        except VerifyMismatchError:
            return jsonify({"erro": "senha_invalida"}), 401

        StepUpReautenticacao.query.filter_by(id_usuario=id_usuario, acao=acao).delete()

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        db.session.add(StepUpReautenticacao(
            id_usuario=id_usuario,
            acao=acao,
            senha_confirmada=True,
            state=state,
            nonce=nonce,
            expira_em=datetime.now(timezone.utc) + timedelta(seconds=DURACAO_REAUTENTICACAO_SEGUNDOS),
        ))
        db.session.commit()

        redirect_uri = url_for("step_up.stepup_google_callback", _external=True)

        autorizacao = oauth.google.create_authorization_url(
            redirect_uri, state=state, nonce=nonce, prompt="login"
        )

        return jsonify({"redirect_url": autorizacao["url"]}), 200

    @staticmethod
    @bp_step_up.route("/google/callback", methods=["GET"])
    def stepup_google_callback():
        """Segunda etapa do fallback: recebe a volta do Google e emite o token.

        Rota própria, separada do callback do login, para não interferir em
        `onboarding_pendente` e `mfa_pendente`. Não exige login porque o
        retorno pode acontecer em outra aba; a correlação é feita pelo `state`.
        Confere que a pendência existe, teve a senha confirmada e não expirou,
        troca o `code` por token, valida o id_token com o `nonce` e exige que o
        e-mail do Google seja o do usuário que confirmou a senha, esteja
        verificado e, se o usuário tiver `google_sub` vinculado, que o `sub`
        seja o mesmo.

        Retorno:
            Redirect para o ponto de entrada do frontend com
            `?token_confirmacao=...&acao=...&expira_em_segundos=...` em
            sucesso, ou com `?erro=` (`reautenticacao_expirada`, `falha_google`
            ou `conta_google_nao_corresponde`) em falha. Em qualquer caso a
            pendência é descartada.
        """
        state = request.args.get("state")
        code = request.args.get("code")
        erro_google = request.args.get("error")

        pendente = StepUpReautenticacao.query.filter_by(state=state).first()

        if erro_google or not pendente or not pendente.senha_confirmada or pendente.expirado():
            return _falhar_reautenticacao(pendente, "reautenticacao_expirada")

        redirect_uri = url_for("step_up.stepup_google_callback", _external=True)

        try:
            token_google = oauth.google.fetch_access_token(redirect_uri=redirect_uri, code=code)
            userinfo = oauth.google.parse_id_token(token_google, nonce=pendente.nonce)
        except Exception:
            return _falhar_reautenticacao(pendente, "falha_google")

        usuario = UsuarioRepository().find_by_id(pendente.id_usuario)

        if (
            not usuario
            or userinfo.get("email") != usuario.email
            or not google_confere_usuario(usuario, userinfo)
        ):
            return _falhar_reautenticacao(pendente, "conta_google_nao_corresponde")

        id_usuario = pendente.id_usuario
        acao = pendente.acao

        db.session.delete(pendente)
        db.session.commit()

        token = _emitir_token(id_usuario, acao)

        return _redirecionar_frontend(
            f"token_confirmacao={token}&acao={acao}&expira_em_segundos={DURACAO_TOKEN_SEGUNDOS}"
        )

    @staticmethod
    def requer_confirmacao_recente(acao):
        """Decorator que exige um token de step-up recente para a rota.

        Uso:
            @app.route("/prontuarios/<id>", methods=["DELETE"])
            @requer_login
            @requer_confirmacao_recente("excluir_prontuario")
            def excluir_prontuario(id):
                ...

        Args:
            acao: identificador da ação sensível protegida.

        Returns:
            Decorator que envolve a view protegida, respondendo 403 com
            `confirmacao_requerida` se o token estiver ausente, incorreto ou
            expirado.
        """
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                if not token_recente_valido(acao):
                    return jsonify({"erro": "confirmacao_requerida", "acao": acao}), 403
                return f(*args, **kwargs)
            return wrapper
        return decorator