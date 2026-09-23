"""Login via Google OAuth (login social, não cria conta nova).

O usuário precisa já existir (cadastrado por um admin) -- o Google
serve apenas para provar posse do e-mail cadastrado, nunca cria conta
automaticamente. Todo login via Google exige confirmação de 2FA
(WebAuthn e/ou TOTP) antes de liberar a sessão, exatamente como o
login por senha (ver login.py e mfa.py): deixar o Google como exceção
permanente equivaleria a um bypass de 2FA (repetir login via Google
para nunca precisar confirmar o segundo fator), agravado por sessões
Google já ativas no navegador (SSO silencioso sem prova nova de
identidade).

O cadastro de WebAuthn/TOTP em si continua fora deste módulo -- é o
onboarding (onboarding.py) que exige escolher pelo menos um dos dois
antes de concluir, independente do primeiro login ter sido por senha
ou por Google.
"""

from flask import Blueprint, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from src.models.usuarios import Usuario
from src.models import db
from src.domains.auth.frontend_config import FRONTEND_URL
from src.domains.auth.onboarding import _usuario_tem_algum_2fa_confirmado

oauth = OAuth()
bp_oauth = Blueprint("oauth", __name__)

# Ponto de entrada fixo e estável no frontend -- não é a página real
# (afterLogin.html), é um pequeno redirecionador. Ver
# frontend/oauth-callback.html. O backend nunca precisa saber onde o
# afterLogin.html realmente mora.
CAMINHO_APOS_LOGIN = "/html/pages/auth/oauth_callback.html"
CAMINHO_LOGIN = "/html/pages/auth/login.html"


def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


class Oauth():

    @staticmethod
    @bp_oauth.route("/login")
    def google_login():
        redirect_uri = url_for("oauth.google_callback", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @staticmethod
    @bp_oauth.route("/callback")
    def google_callback():
        """Recebe o callback do Google e autentica o usuário existente.

        Vincula o `google_sub` na primeira vez que o usuário loga via
        Google. A sessão só é liberada como completa depois de
        confirmado o 2FA (ver mfa.py). `onboarding_pendente` tem
        prioridade sobre `mfa_pendente`: quem ainda não definiu senha
        nem escolheu um método de 2FA precisa passar pelo onboarding
        primeiro (ver onboarding.py) -- não faz sentido pedir 2FA de um
        usuário que ainda não tem nenhum fator cadastrado.

        Retorno:
            Redirect para login.html com erro se o usuário não existir
            ou estiver inativo; redirect para afterLogin.html em sucesso
            (sessão completa OU mfa_pendente OU onboarding_pendente,
            dependendo do estado do usuário) -- ambos na origem do
            frontend (FRONTEND_URL), não na origem do Flask. É o
            afterLogin.js quem decide o que fazer a partir daí, via
            /auth/status -- este módulo não distingue os três casos na
            URL de redirect, só no estado da sessão.
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

        if not usuario.google_sub:
            usuario.google_sub = google_sub
            db.session.commit()

        session.clear()
        session["id_usuario"] = usuario.id
        # is_admin e funcao_clinica são independentes -- mesmo padrão
        # de login.py.
        session["is_admin"] = usuario.is_admin
        session["funcao_clinica"] = usuario.funcao_clinica
        session["uuid_usuario"] = usuario.uuid
        session["is_super_admin"] = usuario.is_super_admin
        session["senha_versao"] = usuario.senha_versao
        session.permanent = True

        # CORRIGIDO: era `or`, deveria ser `and` -- mesmo bug de
        # login.py. Com `or`, um usuário que teve só a senha resetada
        # (hash_senha=None, mas 2FA ainda confirmado) fechava
        # onboarding_pendente na hora, pulando a etapa de definir senha
        # nova -- ficava com hash_senha=None permanentemente, sem
        # nunca ser levado de volta a /definir-senha. Concluir
        # onboarding exige os dois requisitos presentes, mesma regra
        # de onboarding.py::concluir_onboarding().
        if usuario.onboarding_pendente and (usuario.hash_senha and _usuario_tem_algum_2fa_confirmado(usuario.id)):
            usuario.onboarding_pendente = False
            db.session.commit()

        if usuario.onboarding_pendente:
            # Único caso que NÃO passa por 2FA -- usuário ainda não tem
            # nenhum fator cadastrado (nem senha definida, no caso de
            # primeiro acesso). Precisa concluir o onboarding primeiro;
            # é lá que WebAuthn/TOTP são escolhidos (ver onboarding.py).
            session["onboarding_pendente"] = True
        else:
            from src.core.session import iniciar_mfa_pendente
            iniciar_mfa_pendente()

        return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_LOGIN}")