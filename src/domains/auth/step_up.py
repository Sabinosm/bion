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
        # Sem WebAuthn cadastrado -- fluxo alternativo. Não gera nada
        # ainda aqui; só informa ao frontend qual caminho seguir. O
        # registro de reautenticação só é criado em
        # /stepup/senha/confirmar, junto com a validação da senha.
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


@bp_step_up.route("/confirmar", methods=["POST"])
@requer_login
def stepup_confirmar():
    """Valida a assinatura WebAuthn e emite um token de confirmação.

    O token é de uso único, curto e vinculado à ação específica
    definida em `/stepup/iniciar` -- não serve para confirmar nenhuma
    outra ação. Qualquer token anterior da mesma combinação (usuário,
    ação) é removido antes de emitir o novo.

    A `acao` enviada aqui pelo frontend é só conferência: a fonte de
    verdade é a `acao` vinculada ao challenge na sessão, gravada em
    `/stepup/iniciar`. Se não baterem, a confirmação é rejeitada --
    isso impede iniciar o desafio para uma ação e confirmar outra.

    Corpo esperado (JSON): `acao` e `credencial` (resposta WebAuthn).

    Retorno:
        200 com o token de confirmação e seu tempo de expiração.
        400 se a ação não for especificada ou não houver um desafio
        pendente na sessão.
        401 se a credencial não for encontrada, a assinatura for
        inválida, ou a ação não bater com a do desafio iniciado.
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
        # A ação confirmada não é a mesma para a qual o desafio foi
        # gerado -- não deixa o token sair vinculado a algo diferente
        # do que o usuário efetivamente assinou.
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


@bp_step_up.route("/senha/confirmar", methods=["POST"])
@requer_login
def stepup_senha_confirmar():
    """Primeira etapa do fallback: confirma a senha atual do usuário.

    Só deve ser chamada por usuários sem WebAuthn cadastrado -- ver
    `/stepup/iniciar`. Usuários com credencial devem usar o fluxo
    WebAuthn normal; esta rota não impede a chamada por eles, mas o
    frontend não deveria oferecê-la nesse caso.

    Ao validar a senha, cria um registro `StepUpReautenticacao` com
    `senha_confirmada=True` e devolve a URL para redirecionar ao
    Google (segunda etapa). O registro expira em
    `DURACAO_REAUTENTICACAO_SEGUNDOS` -- se o usuário não completar o
    login Google a tempo, precisa reiniciar do zero.

    Corpo esperado (JSON): `acao`, `senha`.

    Retorno:
        200 com `redirect_url` para o Google.
        400 se `acao` ou `senha` não forem informadas.
        401 se a senha estiver incorreta.
    """
    id_usuario = get_id_usuario_sessao()
    dados = request.get_json(silent=True) or {}
    acao = dados.get("acao")
    senha = dados.get("senha")

    if not acao or not senha:
        return jsonify({"erro": "dados_incompletos"}), 400

    usuario = get_usuario_sessao()

    if not usuario or not usuario.hash_senha:
        # Usuário sem senha definida (só login via Google) não tem
        # como confirmar por este método -- nada a fazer aqui além de
        # recusar; o frontend deveria nem oferecer esta opção nesse
        # caso.
        return jsonify({"erro": "senha_nao_definida"}), 400

    try:
        ph.verify(usuario.hash_senha, senha)
    except VerifyMismatchError:
        return jsonify({"erro": "senha_invalida"}), 401

    # Qualquer reautenticação pendente anterior da mesma combinação
    # (usuário, ação) é substituída -- evita acumular registros de
    # tentativas abandonadas.
    StepUpReautenticacao.query.filter_by(id_usuario=id_usuario, acao=acao).delete()

    state = secrets.token_urlsafe(32)
    db.session.add(StepUpReautenticacao(
        id_usuario=id_usuario,
        acao=acao,
        senha_confirmada=True,
        state=state,
        expira_em=datetime.now(timezone.utc) + timedelta(seconds=DURACAO_REAUTENTICACAO_SEGUNDOS),
    ))
    db.session.commit()

    redirect_uri = url_for("step_up.stepup_google_callback", _external=True)

    # TODO: confirmar o método exato do Authlib para gerar a URL de
    # autorização SEM disparar um redirect 302 (diferente de
    # oauth.google.authorize_redirect(), usado em oauth.py, que já
    # retorna uma Response 302 pronta -- não serve aqui porque esta
    # rota é chamada via fetch() e precisa devolver JSON para o
    # frontend decidir a navegação, não uma resposta HTTP de redirect).
    #
    # `create_authorization_url` é o nome no client OAuth2 puro do
    # Authlib (authlib.integrations.requests_client / httpx_client),
    # mas o objeto `oauth.google` aqui é o wrapper Flask
    # (FlaskOAuth2App) -- a API pode não ser idêntica. Para confirmar
    # na versão instalada:
    #
    #   python3 -c "
    #   from authlib.integrations.flask_client import OAuth
    #   import inspect
    #   print([m for m in dir(OAuth) if 'author' in m.lower()])
    #   "
    #
    # ou inspecionar diretamente a classe de oauth.google (FlaskOAuth2App)
    # no ambiente do projeto. Se o nome for outro, só trocar a chamada
    # abaixo -- o resto do fluxo (state, prompt=login, callback) não muda.
    autorizacao = oauth.google.create_authorization_url(
        redirect_uri, state=state, prompt="login"
    )

    return jsonify({"redirect_url": autorizacao["url"]}), 200


@bp_step_up.route("/google/callback", methods=["GET"])
def stepup_google_callback():
    """Segunda etapa do fallback: recebe a volta do Google e emite o token.

    Rota própria, separada do callback de login (`oauth.google_callback`)
    -- não deve reautenticar a sessão nem tratar onboarding/MFA, só
    concluir a reconfirmação de uma ação específica já em andamento.

    `state` é a mesma correlação usada para localizar o registro
    `StepUpReautenticacao` -- confirma que este callback corresponde
    ao redirect que a etapa anterior gerou, e não a qualquer outro.

    `prompt=login` foi exigido no redirect (ver stepup_senha_confirmar)
    para que este login ao Google seja uma reautenticação real, não um
    SSO silencioso reaproveitando uma sessão Google já aberta no
    navegador -- sem isso, a segunda "prova" não provaria nada de novo.

    Retorno:
        Redirect para `stepup_callback.html` no frontend, com
        `token_confirmacao` e `acao` na query string em caso de
        sucesso, ou `erro` em caso de falha.
    """
    state = request.args.get("state")

    pendente = StepUpReautenticacao.query.filter_by(state=state).first()

    if not pendente or not pendente.senha_confirmada or pendente.expirado():
        db.session.delete(pendente) if pendente else None
        db.session.commit()
        return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_REAUTENTICACAO}?erro=reautenticacao_expirada")

    # TODO: authorize_access_token() normalmente valida o `state` de
    # volta contra um valor que o próprio Authlib gravou na sessão
    # Flask durante authorize_redirect()/create_authorization_url().
    # Como o redirect original foi gerado sem passar pela sessão deste
    # navegador de forma garantida (ver TODO em stepup_senha_confirmar),
    # essa validação interna do Authlib pode falhar mesmo com o state
    # já conferido manualmente acima contra StepUpReautenticacao.
    # Se authorize_access_token() lançar erro de state/CSRF em teste,
    # a correção provável é usar fetch_access_token() ou o client
    # OAuth2 de baixo nível diretamente, passando o `code` e `state`
    # da query string explicitamente, sem depender da sessão.
    token_google = oauth.google.authorize_access_token()
    userinfo = token_google["userinfo"]

    usuario = ur.find_by_id(pendente.id_usuario)

    # O e-mail que voltou do Google precisa ser o mesmo do usuário que
    # iniciou o fluxo (confirmou a senha na etapa anterior) -- sem
    # isso, alguém poderia confirmar a senha de uma conta e completar
    # a segunda etapa logado com uma conta Google diferente.
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


def requer_confirmacao_recente(acao):
    """Decorator que exige um token de step-up recente para a rota.

    O frontend deve enviar o token no header `X-Stepup-Token`. O token
    é consumido (apagado) assim que validado, mesmo que a ação decorada
    falhe depois por outro motivo -- evitando reuso. Funciona
    identicamente para tokens emitidos via WebAuthn ou via senha+Google
    -- o decorator não distingue a origem.

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