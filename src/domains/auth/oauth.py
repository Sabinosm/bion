"""Login via Google OAuth (login social, não cria conta nova).

O usuário precisa já existir (cadastrado por um admin). O Google aqui
serve apenas para provar posse do e-mail cadastrado -- nunca cria conta
automaticamente.

Login via Google NUNCA exige WebAuthn/2FA
-------------------------------------------
Diferente do login por senha (login.py), autenticar com sucesso via
Google já é, em si, uma prova forte de identidade -- por isso o login
via Google libera a sessão como completa direto após o callback,
mesmo que o usuário tenha uma credencial WebAuthn cadastrada. O único
bloqueio possível é o onboarding pendente (usuário ainda sem senha
definida), que tem prioridade sobre tudo.

O cadastro de WebAuthn deixa de ser parte do onboarding (ver
onboarding.py) e passa a ser feito depois, nas configurações da
conta -- quem cadastrar poderá usá-lo para 2FA em logins futuros por
senha, mas isso nunca afeta o login por Google.

CORRIGIDO (bugs pré-existentes, sem relação com a migração FHIR):
1. `usuario.ativo` não existe no model -- o campo real é `status`
   (enum 'ativo'/'inativo'/'suspenso'). Corrigido para status == "ativo".
2. `usuario.id_usuario` não existe como atributo Python -- o model
   mapeia a coluna `id_usuario` do banco para o atributo `.id`.
   Corrigido para usuario.id.
3. `google_callback` não tinha decorator de rota (@bp_oauth.route),
   então nunca foi registrada como endpoint Flask -- url_for(
   "oauth.google_callback") em google_login() falhava com BuildError.
   Corrigido adicionando @bp_oauth.route("/callback").
4. Os redirects finais usavam paths relativos como
   "/paginas/pos-login.html", que o navegador resolve contra a
   origem ATUAL no momento do redirect -- e essa origem é o Flask
   (localhost:5000), não o frontend, que roda num servidor separado
   (Vite/live-server, ex. localhost:5500 em dev). Isso fazia o
   redirect apontar para uma página que não existe no Flask.
   Corrigido para montar a URL completa a partir de FRONTEND_URL
   (frontend_config.py).
5. O destino do redirect de sucesso apontava direto para o path
   físico do afterLogin.html (html/pages/auth/afterLogin.html) --
   acoplando este arquivo à estrutura interna de pastas do frontend.
   Se o frontend reorganizar arquivos, este backend quebraria
   silenciosamente (só um redirect errado, sem erro de compilação
   avisando). Trocado por um destino genérico e estável,
   "/oauth-callback.html", que existe só para esse propósito -- ver
   frontend/oauth-callback.html, que faz o redirect real para onde o
   afterLogin.html estiver hoje. Esse arquivo nunca deveria precisar
   mudar de path.

ALTERADO (múltiplos admins por empresa):
- `session["is_super_admin"]` passa a ser gravado aqui também, no
  ramo em que a sessão é liberada por completo (sem onboarding
  pendente) -- mesmo motivo de login.py. Não é gravado no ramo de
  onboarding_pendente porque, nesse caso, a sessão ainda não está
  completa e onboarding.py grava o restante ao concluir; ver nota lá.
"""

from flask import Blueprint, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from src.models.usuarios import Usuario
from src.models import db
from src.domains.auth.frontend_config import FRONTEND_URL

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

        Vincula o `google_sub` na primeira vez que o usuário loga via Google.
        Define o próximo estado da sessão conforme o usuário já tenha
        concluído o onboarding (senha definida) ou não.

        Não passa por `mfa_pendente` em nenhum caso -- login via Google
        libera a sessão como completa direto (exceto onboarding pendente),
        mesmo que o usuário tenha WebAuthn cadastrado. Ver docstring do
        módulo para o racional.

        Retorno:
            Redirect para login.html com erro se o usuário não existir
            ou estiver inativo; redirect para afterLogin.html em sucesso
            -- ambos na origem do frontend (FRONTEND_URL), não na origem
            do Flask.
        """
        token = oauth.google.authorize_access_token()
        userinfo = token["userinfo"]

        email = userinfo["email"]
        google_sub = userinfo["sub"]

        usuario = Usuario.query.filter_by(email=email).first()
        if not usuario:
            return redirect(f"{FRONTEND_URL}{CAMINHO_LOGIN}?erro=usuario_nao_cadastrado")

        # CORRIGIDO: era usuario.ativo (atributo inexistente) -> usuario.status
        if usuario.status != "ativo":
            return redirect(f"{FRONTEND_URL}{CAMINHO_LOGIN}?erro=conta_inativa")

        if not usuario.google_sub:
            usuario.google_sub = google_sub
            db.session.commit()

        session.clear()
        # CORRIGIDO: era usuario.id_usuario (atributo inexistente) -> usuario.id
        session["id_usuario"] = usuario.id
        session["tipo_usuario"] = usuario.tipo_usuario
        session["uuid_usuario"] = usuario.uuid
        # ADICIONADO: mesmo motivo de login.py -- necessário pra
        # g.is_super_admin e requer_super_admin funcionarem depois.
        session["is_super_admin"] = usuario.is_super_admin
        session.permanent = True

        if usuario.onboarding_pendente:
            # Único bloqueio possível para login via Google: falta definir
            # senha. WebAuthn não faz mais parte do onboarding (ver
            # onboarding.py), então não há mais nada além da senha
            # pendente aqui.
            session["onboarding_pendente"] = True
        else:
            # Login via Google sempre libera sessão completa, mesmo que o
            # usuário tenha WebAuthn cadastrado -- ver docstring do módulo.
            session["id_empresa"] = usuario.id_empresa

        return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_LOGIN}")