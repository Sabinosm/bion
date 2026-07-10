"""Login via Google OAuth (login social, não cria conta nova).

O usuário precisa já existir (cadastrado por um admin). O Google aqui
serve apenas para provar posse do e-mail cadastrado -- nunca cria conta
automaticamente.
"""

from flask import Blueprint, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from src.models.usuarios import Usuario
from src.models import db

oauth = OAuth()
bp_oauth = Blueprint("oauth", __name__)


def init_oauth(app):
    """Registra o provedor Google no cliente OAuth da aplicação.

    Parâmetros:
        app: instância da aplicação Flask, de onde são lidas as
            credenciais `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`.
    """
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@bp_oauth.route("/auth/google/login")
def google_login():
    """Inicia o fluxo OAuth redirecionando o navegador para o Google.

    Retorno:
        Redirect HTTP para a tela de autorização do Google.
    """
    redirect_uri = url_for("oauth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp_oauth.route("/auth/google/callback")
def google_callback():
    """Recebe o callback do Google e autentica o usuário existente.

    Vincula o `google_sub` na primeira vez que o usuário loga via Google.
    Define o próximo estado da sessão conforme o usuário já tenha
    concluído o onboarding (senha + WebAuthn) ou não.

    Esta rota é alcançada por navegação real do navegador (redirect do
    Google), não por fetch -- por isso responde com redirects para
    páginas HTML fixas, que do lado do cliente consultam `/auth/status`
    ou `/auth/me` via fetch para decidir o próximo passo.

    Retorno:
        Redirect para `login.html` com erro se o usuário não existir
        ou estiver inativo; redirect para `pos-login.html` em sucesso.
    """
    token = oauth.google.authorize_access_token()
    userinfo = token["userinfo"]

    email = userinfo["email"]
    google_sub = userinfo["sub"]

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return redirect("/paginas/login.html?erro=usuario_nao_cadastrado")

    if not usuario.ativo:
        return redirect("/paginas/login.html?erro=conta_inativa")

    if not usuario.google_sub:
        usuario.google_sub = google_sub
        db.session.commit()

    session.clear()
    session["id_usuario"] = usuario.id_usuario

    if usuario.onboarding_pendente:
        session["onboarding_pendente"] = True
        session.permanent = True
    else:
        session["mfa_pendente"] = True
        session.permanent = True

    return redirect("/paginas/pos-login.html")