"""Step-up authentication.

Reconfirma a identidade antes de ações sensíveis (excluir prontuário,
alterar prescrição, conceder acesso admin), mesmo com a sessão já
totalmente autenticada.

Dois métodos, conforme o que o usuário tem cadastrado
---------------------------------------------------------
1. WebAuthn (preferencial): gera um desafio vinculado ao `id_usuario`
   e à ação específica. Só disponível para quem já tem credencial
   cadastrada.

2. Senha + Google (fallback para quem não tem WebAuthn): em duas
   etapas -- primeiro confirma a senha atual, depois reautentica via
   Google com `prompt=login` (forçando o Google a pedir login de novo,
   mesmo que já haja uma sessão Google ativa no navegador -- sem isso,
   a "reautenticação" poderia ser só um SSO silencioso que não prova
   nada de novo). O estado entre essas duas etapas é persistido na
   tabela `stepup_reautenticacao` (não na sessão Flask), porque o
   fluxo atravessa um redirect real de navegador e pode voltar em uma
   aba diferente da que iniciou.

   Isso é deliberadamente mais fraco que WebAuthn: senha + Google prova
   posse de duas credenciais que já autenticaram a sessão original (não
   é um fator independente), enquanto WebAuthn prova posse de hardware
   específico. É o preço aceito para não deixar usuários sem WebAuthn
   irrecuperavelmente incapazes de confirmar ações sensíveis.

Em ambos os casos, o resultado final é o mesmo: um token de curta
duração vinculado ao `id_usuario` e à ação, guardado na tabela
`stepup_token`. A rota sensível exige esse token via decorator
`requer_confirmacao_recente`, que não precisa saber qual dos dois
métodos foi usado para obtê-lo.

ALTERADO (separação admin/papel clínico): extraída a função
`token_recente_valido(acao)`, com a MESMA lógica que já vivia dentro
do wrapper de `requer_confirmacao_recente`. Motivo: `usuario/controller.py`
precisa da mesma checagem de forma CONDICIONAL dentro de `atualizar()`
-- só quando o payload mexe em campos sensíveis (eh_admin/tipo_papel),
não a rota inteira. Um decorator estático não serve para esse caso; a
função nomeada serve para os dois usos (decorator e checagem manual)
sem duplicar a query/validação de token.
"""

import base64
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, session, redirect, url_for

from argon2.exceptions import VerifyMismatchError

from src.models import db
from src.models.usuarios import CredencialWebAuthn, Usuario
from src.models.auditoria.stepup import StepUpToken
from src.models.auditoria.stepup_reautenticacao import StepUpReautenticacao
from src.core.security import ph
from src.core.session import requer_login, get_usuario_sessao, get_id_usuario_sessao
from src.domains.auth.webauthn_config import RP_ID, EXPECTED_ORIGIN
from src.domains.auth.frontend_config import FRONTEND_URL
from src.domains.auth.oauth import oauth

from webauthn import generate_authentication_options, verify_authentication_response, options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
from src.domains.usuario.repository import UsuarioRepository as ur
bp_step_up = Blueprint("step_up", __name__)

DURACAO_TOKEN_SEGUNDOS = 180
DURACAO_REAUTENTICACAO_SEGUNDOS = 300

# Ponto de entrada estático no frontend para onde o callback de
# reautenticação redireciona ao terminar -- mesmo padrão de
# oauth.py (CAMINHO_APOS_LOGIN): o backend nunca precisa conhecer a
# estrutura interna de pastas do frontend, só esse arquivo físico.
CAMINHO_APOS_REAUTENTICACAO = "/html/pages/auth/stepup_callback.html"


def _emitir_token(id_usuario, acao):
        """Apaga qualquer token anterior da mesma combinação (usuário,
        ação) e emite um StepUpToken novo. Compartilhado pelos dois
        métodos de confirmação (WebAuthn e senha+Google).
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
    """Verifica e CONSOME (apaga) um token de step-up recente para a
    ação informada, lendo o header X-Stepup-Token da requisição atual.

    ADICIONADO (separação admin/papel clínico): extraído do corpo do
    wrapper de `requer_confirmacao_recente` para poder ser chamado
    tanto pelo decorator (uso normal, rota inteira sensível) quanto
    de forma condicional dentro de uma view que só é sensível às
    vezes, dependendo do payload (ex: UsuarioController.atualizar,
    que também edita campos triviais no mesmo endpoint).

    Mesma semântica de sempre: token de uso único -- é apagado assim
    que lido, independente do resultado, para não permitir reuso.

    Retorno:
        True se havia um token válido e não expirado (e ele já foi
        consumido/apagado). False caso contrário (ausente, incorreto
        ou expirado) -- quem chama decide o que fazer (normalmente,
        responder 403 com "confirmacao_requerida").
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


class StepUp():
    
    @staticmethod
    @bp_step_up.route("/iniciar", methods=["POST"])
    @requer_login
    def stepup_iniciar():
        """Inicia a reconfirmação de identidade, no método disponível para o usuário.

        Chamado pelo frontend quando uma rota sensível responde 403 com
        `confirmacao_requerida`.

        A `acao` é exigida já aqui (não só na confirmação) e fica vinculada
        ao desafio gerado. Isso impede que alguém inicie um step-up para
        uma ação e confirme com `acao` diferente na segunda chamada.

        Corpo esperado (JSON): `acao`.

        Retorno:
            200 com `metodo: "webauthn"` e as opções de autenticação, se o
            usuário tiver credencial cadastrada.
            200 com `metodo: "senha_google"` se o usuário não tiver
            credencial cadastrada -- o frontend deve seguir para
            `/stepup/senha/confirmar`.
            400 se `acao` não for informada.
        """
        id_usuario = get_id_usuario_sessao()

        dados = request.get_json(silent=True) or {}
        acao = dados.get("acao")
        if not acao:
            return jsonify({"erro": "acao_nao_especificada"}), 400

        credenciais = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).all()

        if not credenciais:
            return jsonify({"metodo": "senha_google", "acao": acao}), 200

        permitir = [
            PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
            for c in credenciais
        ]

        opcoes = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=permitir,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        session["stepup_challenge"] = {
            "challenge": base64.b64encode(opcoes.challenge).decode(),
            "acao": acao,
        }

        corpo = {"metodo": "webauthn"}
        import json
        corpo.update(json.loads(options_to_json(opcoes)))
        return jsonify(corpo), 200


    @staticmethod
    @bp_step_up.route("/confirmar", methods=["POST"])
    @requer_login
    def stepup_confirmar():
        """Valida a assinatura WebAuthn e emite um token de confirmação."""
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
        """Primeira etapa do fallback: confirma a senha atual do usuário."""
        id_usuario = get_id_usuario_sessao()
        dados = request.get_json(silent=True) or {}
        acao = dados.get("acao")
        senha = dados.get("senha")

        if not acao or not senha:
            return jsonify({"erro": "dados_incompletos"}), 400

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
        """Segunda etapa do fallback: recebe a volta do Google e emite o token."""
        state = request.args.get("state")
        code = request.args.get("code")
        erro_google = request.args.get("error")

        pendente = StepUpReautenticacao.query.filter_by(state=state).first()

        if erro_google or not pendente or not pendente.senha_confirmada or pendente.expirado():
            db.session.delete(pendente) if pendente else None
            db.session.commit()
            return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_REAUTENTICACAO}?erro=reautenticacao_expirada")

        redirect_uri = url_for("step_up.stepup_google_callback", _external=True)

        try:
            token_google = oauth.google.fetch_access_token(
                redirect_uri=redirect_uri,
                code=code,
            )
        except Exception:
            db.session.delete(pendente)
            db.session.commit()
            return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_REAUTENTICACAO}?erro=falha_google")

        try:
            userinfo = oauth.google.parse_id_token(token_google, nonce=pendente.nonce)
        except Exception:
            db.session.delete(pendente)
            db.session.commit()
            return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_REAUTENTICACAO}?erro=falha_google")

        usuario = ur.find_by_id(pendente.id_usuario)

        if not usuario or userinfo.get("email") != usuario.email:
            db.session.delete(pendente)
            db.session.commit()
            return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_REAUTENTICACAO}?erro=conta_google_nao_corresponde")

        id_usuario = pendente.id_usuario
        acao = pendente.acao

        db.session.delete(pendente)
        db.session.commit()

        token = _emitir_token(id_usuario, acao)

        return redirect(
            f"{FRONTEND_URL}{CAMINHO_APOS_REAUTENTICACAO}"
            f"?token_confirmacao={token}&acao={acao}&expira_em_segundos={DURACAO_TOKEN_SEGUNDOS}"
        )

    @staticmethod
    def requer_confirmacao_recente(acao):
        """Decorator que exige um token de step-up recente para a rota.

        ALTERADO: o corpo do wrapper agora delega para
        `token_recente_valido(acao)` -- mesma função usada para a
        checagem condicional em UsuarioController.atualizar(). Zero
        mudança de comportamento aqui, só eliminação de duplicação.

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
                if not token_recente_valido(acao):
                    return jsonify({"erro": "confirmacao_requerida", "acao": acao}), 403
                return f(*args, **kwargs)
            return wrapper
        return decorator