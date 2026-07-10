# auth/oauth.py
from flask import Blueprint, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from src.models.usuarios import Usuario
from src.models import db

oauth = OAuth()
bp_oauth = Blueprint("oauth", __name__)


def init_oauth(app):
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
    redirect_uri = url_for("oauth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp_oauth.route("/auth/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token["userinfo"]

    email = userinfo["email"]
    google_sub = userinfo["sub"]

    # o usuário TEM que já existir (cadastrado pelo admin).
    # Google aqui só serve para provar "esta pessoa é dona deste email" —
    # ele NUNCA cria conta nova sozinho.
    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        
        # Bion só responde JSON — mas esta rota é alcançada por
        # NAVEGAÇÃO REAL do navegador (redirect do Google), não por
        # fetch. Por isso redireciona para uma página fixa que, do
        # lado do cliente, faz um fetch em /auth/me e trata o erro.
        return redirect("/paginas/login.html?erro=usuario_nao_cadastrado")

    if not usuario.ativo:
        return redirect("/paginas/login.html?erro=conta_inativa")

    # Vincula o google_sub na primeira vez (próximos logins via Google
    # poderiam usar direto o sub, mas o e-mail já cumpre o papel aqui)
    if not usuario.google_sub:
        usuario.google_sub = google_sub
        db.session.commit()

    session.clear()
    session["id_usuario"] = usuario.id_usuario

    if usuario.onboarding_pendente:
        # Ainda não definiu senha nem cadastrou WebAuthn.
        # Sessão fica restrita só às rotas de onboarding.
        session["onboarding_pendente"] = True
        session.permanent = True
    else:
        # Onboarding já concluído: login por Google recorrente ainda
        # assim respeita a política de 2FA obrigatório (WebAuthn)
        session["mfa_pendente"] = True
        session.permanent = True

    # A sessão (cookie httpOnly) já está gravada neste ponto — a página
    # de destino descobre o status via fetch em /auth/me (JSON), não
    # por este redirect carregar dados. O redirect aqui é só navegação.
    return redirect("/paginas/pos-login.html")