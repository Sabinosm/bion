"""Login via Google OAuth (login social, não cria conta nova).

O usuário precisa já existir (cadastrado por um admin). O Google aqui
serve apenas para provar posse do e-mail cadastrado -- nunca cria conta
automaticamente.

CORRIGIDO (bugs pré-existentes, sem relação com a migração FHIR):
1. `usuario.ativo` não existe no model -- o campo real é `status`
   (enum 'ativo'/'inativo'/'suspenso'). Corrigido para status == "ativo".
2. `usuario.id_usuario` não existe como atributo Python -- o model
   mapeia a coluna `id_usuario` do banco para o atributo `.id`.
   Corrigido para usuario.id.
"""

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


@bp_oauth.route("/login")
def google_login():
    redirect_uri = url_for("oauth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp_oauth.route("/callback")
def google_callback():
    """Recebe o callback do Google e autentica o usuário existente.

    Vincula o `google_sub` na primeira vez que o usuário loga via Google.
    Define o próximo estado da sessão conforme o usuário já tenha
    concluído o onboarding (senha + WebAuthn) ou não.

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

    # CORRIGIDO: era usuario.ativo (atributo inexistente) -> usuario.status
    if usuario.status != "ativo":
        return redirect("/paginas/login.html?erro=conta_inativa")

    if not usuario.google_sub:
        usuario.google_sub = google_sub
        db.session.commit()

    session.clear()
    # CORRIGIDO: era usuario.id_usuario (atributo inexistente) -> usuario.id
    session["id_usuario"] = usuario.id

    if usuario.onboarding_pendente:
        session["onboarding_pendente"] = True
        session.permanent = True
    else:
        session["mfa_pendente"] = True
        session.permanent = True

    return redirect("/paginas/pos-login.html")