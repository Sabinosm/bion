"""Login via Google OAuth (login social, não cria conta nova).

O usuário precisa já existir (cadastrado por um admin). O Google aqui
serve apenas para provar posse do e-mail cadastrado -- nunca cria conta
automaticamente.

ALTERADO (2FA sempre obrigatório, também via Google)
-------------------------------------------------------
Versão anterior deste módulo liberava a sessão como completa direto
após o callback do Google, sem passar por 2FA -- autenticar com
sucesso via Google era tratado como prova forte o suficiente por si
só. Essa exceção foi removida: agora TODO login, por senha ou por
Google, exige confirmação de 2FA (WebAuthn e/ou TOTP) antes de liberar
a sessão -- ver login.py e mfa.py para o mesmo tratamento do lado do
login por senha.

Motivo da mudança: com WebAuthn e/ou TOTP agora obrigatórios desde o
onboarding (ver onboarding.py), todo usuário tem pelo menos um fator
cadastrado. Deixar o Google como exceção permanente teria virado, na
prática, um bypass permanente de 2FA -- bastaria repetir login via
Google para nunca precisar confirmar o segundo fator. Navegadores que
mantêm sessão Google ativa (login social "lembrado") agravavam isso:
a "reautenticação" via Google podia ser só um SSO silencioso, sem
nenhuma prova nova de identidade.

O cadastro de WebAuthn/TOTP continua fora do onboarding por senha em
si (ver onboarding.py) -- é o onboarding, de forma geral, que agora
exige escolher pelo menos um dos dois antes de concluir, independente
de o primeiro login ter sido por senha ou por Google.

CORRIGIDO (bugs pré-existentes, sem relação com a migração FHIR nem
com esta mudança de 2FA -- mantidos aqui por não terem sido
revertidos):
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

ADICIONADO (checagem de sessão obsoleta em leituras sensíveis -- ver
requer_senha_atualizada em session.py):
- `session["senha_versao"]` passa a ser gravada aqui também, mesmo
  snapshot gravado em login.py, agora também no caminho Google.
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

        Vincula o `google_sub` na primeira vez que o usuário loga via Google.

        ALTERADO: assim como no login por senha, a sessão só é liberada
        como completa depois de confirmado o 2FA (WebAuthn e/ou TOTP) --
        ver mfa.py. `onboarding_pendente` continua tendo prioridade
        sobre `mfa_pendente`: quem ainda não definiu senha nem escolheu
        um método de 2FA precisa passar pelo onboarding primeiro (ver
        onboarding.py), não faz sentido pedir 2FA de um usuário que
        ainda não tem nenhum fator cadastrado.

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

        # CORRIGIDO: era usuario.ativo (atributo inexistente) -> usuario.status
        if usuario.status == "inativo":
            return redirect(f"{FRONTEND_URL}{CAMINHO_LOGIN}?erro=conta_inativa")

        if not usuario.google_sub:
            usuario.google_sub = google_sub
            db.session.commit()

        session.clear()
        # CORRIGIDO: era usuario.id_usuario (atributo inexistente) -> usuario.id
        session["id_usuario"] = usuario.id
        # ALTERADO (assertivo, sem alias): mesmo padrão de login.py —
        # session["tipo_usuario"] saiu, is_admin + funcao_clinica entram.
        session["is_admin"] = usuario.is_admin
        session["funcao_clinica"] = usuario.funcao_clinica
        session["uuid_usuario"] = usuario.uuid
        # ADICIONADO: mesmo motivo de login.py -- necessário pra
        # g.is_super_admin e requer_super_admin funcionarem depois.
        session["is_super_admin"] = usuario.is_super_admin
        # ADICIONADO (checagem de sessão obsoleta em leituras sensíveis
        # -- ver requer_senha_atualizada em session.py): mesmo snapshot
        # gravado em login.py, agora também no caminho Google.
        session["senha_versao"] = usuario.senha_versao
        session.permanent = True

        # CORRIGIDO: mesmo problema e mesma correção de login.py --
        # `onboarding_pendente` só era fechado dentro de
        # /onboarding/concluir, uma chamada HTTP separada da
        # confirmação do 2FA. Se essa chamada nunca acontecesse (sessão
        # caindo no meio do caminho), o usuário ficava preso em
        # onboarding_pendente para sempre, mesmo com senha e 2FA já
        # prontos no banco. Fechamos aqui também quando os
        # pré-requisitos já estão satisfeitos.
        if usuario.onboarding_pendente and usuario.hash_senha or _usuario_tem_algum_2fa_confirmado(usuario.id):
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
            # ALTERADO: login via Google agora também exige 2FA, igual
            # ao login por senha -- ver docstring do módulo. A sessão
            # fica pendente até a confirmação via /webauthn/2fa/confirmar
            # ou /totp/2fa/confirmar (mesmas rotas usadas pelo login por
            # senha, ver webauthn_2fa.py e totp_2fa.py).
            iniciar_mfa_pendente()  # era: session["mfa_pendente"] = True

        return redirect(f"{FRONTEND_URL}{CAMINHO_APOS_LOGIN}")