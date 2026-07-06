# auth/oauth.py
from flask import Blueprint, session, redirect, jsonify, url_for
from authlib.integrations.flask_client import OAuth
from src.database.usuarios import Usuario
from src.database import db
from src.domains.configuracao.service import ConfiguracaoService
from src.core.responses import json_success

 
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
 
 
 # FIXME
@bp_oauth.route("/google/login")
def google_login():
    redirect_uri = url_for("oauth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)
 
 
@bp_oauth.route("/google/callback")
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
        return jsonify({"erro": "usuario_nao_cadastrado"}), 403
 
    if not usuario.ativo:
        return jsonify({"erro": "conta_inativa"}), 403
 
    # Vincula o google_sub na primeira vez (próximos logins via Google
    # poderiam usar direto o sub, mas o e-mail já cumpre o papel aqui)
    
    if not usuario.google_sub:
        usuario.google_sub = google_sub
        db.session.commit()
 
    session.clear()
    session["id_usuario"] = usuario.id
 
    if usuario.onboarding_pendente:
        # Ainda não definiu senha nem cadastrou WebAuthn.
        # Sessão fica restrita só às rotas de onboarding.
        
        session["onboarding_pendente"] = True
        session.permanent = True
        return jsonify({"status": "onboarding_requerido"}), 200
 
    # Onboarding já concluído: login por Google recorrente ainda assim
    # respeita a política de 2FA obrigatório (WebAuthn)
    
    session["mfa_pendente"] = True
    session.permanent = True
    return jsonify({"status": "mfa_requerido", "metodo": "webauthn"}), 200


