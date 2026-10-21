"""
oauth.py

Login social via Google OAuth. Não cria conta nova: o usuário precisa já
existir, cadastrado por um admin, e o Google serve apenas para provar a posse
do e-mail cadastrado.

Todo login via Google exige confirmação de 2FA (WebAuthn e/ou TOTP) antes de
liberar a sessão, exatamente como o login por senha. Deixar o Google como
exceção permanente seria um bypass de 2FA: bastaria repetir o login pelo
Google para nunca confirmar o segundo fator, agravado por sessões Google já
ativas no navegador (SSO silencioso, sem prova nova de identidade).

O cadastro de WebAuthn e TOTP continua fora deste módulo, no onboarding, que
exige escolher ao menos um dos dois antes de concluir, independentemente de o
primeiro login ter sido por senha ou por Google.
"""

from flask import Blueprint, current_app, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from src.models.usuarios import Usuario
from src.models import db
from src.domains.auth.frontend_config import FRONTEND_URL
from src.domains.auth.onboarding import onboarding_ainda_pendente

oauth = OAuth()
bp_oauth = Blueprint("oauth", __name__)

# Ponto de entrada fixo e estável no frontend: não é a página real pós-login,
# e sim um pequeno redirecionador. O backend nunca precisa saber onde a página
# final realmente mora.
CAMINHO_APOS_LOGIN = "/html/pages/auth/oauth_callback.html"
CAMINHO_LOGIN = "/html/pages/auth/login.html"


def init_oauth(app):
    """Registra o cliente Google (OpenID Connect) usando as credenciais da configuração da aplicação."""
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def google_confere_usuario(usuario, userinfo) -> bool:
    """Confere se a identidade devolvida pelo Google é mesmo a do usuário.

    Exige e-mail verificado pelo Google e, se o usuário já tiver `google_sub`
    vinculado, que o `sub` devolvido seja o mesmo. O e-mail sozinho não basta:
    ele pode ser reaproveitado por outra conta Google ao longo do tempo, ao
    passo que o `sub` é o identificador estável da conta.
    """
    if not userinfo.get("email_verified"):
        return False
    return not usuario.google_sub or usuario.google_sub == userinfo.get("sub")


class Oauth():

    @staticmethod
    @bp_oauth.route("/login")
    def google_login():
        """Redireciona o navegador para a tela de autorização do Google.

        A URI de retorno vem de `GOOGLE_REDIRECT_URI` na configuração; sem ela,
        usa a rota de callback deste módulo.
        """
        redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(
            "oauth.google_callback", _external=True
        )
        return oauth.google.authorize_redirect(redirect_uri)

    @staticmethod
    @bp_oauth.route("/callback")
    def google_callback():
        """Recebe o callback do Google e autentica o usuário já cadastrado.

        Exige e-mail verificado e vincula o `google_sub` na primeira vez que o
        usuário entra pelo Google; nas seguintes, o `sub` precisa ser o mesmo.
        A sessão é reiniciada com a identidade e os privilégios do usuário
        (`is_admin` e `funcao_clinica` são independentes, como em login.py) e
        só vira completa depois do 2FA. `onboarding_pendente` tem prioridade
        sobre `mfa_pendente`: quem ainda não definiu senha nem escolheu um
        método de 2FA passa pelo onboarding primeiro, pois não faz sentido
        pedir 2FA de quem não tem fator cadastrado.

        Retorno:
            Redirect para a tela de login do frontend com `?erro=` se o
            usuário não estiver cadastrado (`usuario_nao_cadastrado`), estiver
            inativo (`conta_inativa`) ou a identidade do Google não conferir
            (`conta_google_invalida`: e-mail não verificado ou `sub` diferente
            do vinculado).
            Redirect para o ponto de entrada pós-login do frontend em sucesso,
            com a sessão em estado completa, `mfa_pendente` ou
            `onboarding_pendente`. Os redirects usam FRONTEND_URL, não a
            origem do Flask. A URL não distingue os três casos: é o frontend
            que consulta `/auth/status` e decide o próximo passo.
        """
        token = oauth.google.authorize_access_token()
        userinfo = token["userinfo"]

        email = userinfo["email"]
        google_sub = userinfo["sub"]

        usuario = Usuario.query.filter_by(email=email).first()
        if not usuario:
            return redirect(f"{FRONTEND_URL}{CAMINHO_LOGIN}?erro=usuario_nao_cadastrado")

        if usuario.status == "inativo":
            return redirect(f"{FRONTEND_URL}{CAMINHO_LOGIN}?erro=conta_inativa")

        if not google_confere_usuario(usuario, userinfo):
            return redirect(f"{FRONTEND_URL}{CAMINHO_LOGIN}?erro=conta_google_invalida")

        if not usuario.google_sub:
            usuario.google_sub = google_sub
            db.session.commit()

        session.clear()
        session["id_usuario"] = usuario.id
        session["is_admin"] = usuario.is_admin
        session["funcao_clinica"] = usuario.funcao_clinica
        session["uuid_usuario"] = usuario.uuid
        session["is_super_admin"] = usuario.is_super_admin
        session["senha_versao"] = usuario.senha_versao
        session.permanent = True

        if onboarding_ainda_pendente(usuario):
            session["onboarding_pendente"] = True
        else:
            from src.core.session import iniciar_mfa_pendente
            iniciar_mfa_pendente()

        return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_LOGIN}")