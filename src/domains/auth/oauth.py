# auth/oauth.py
from flask import Blueprint, session, redirect, jsonify, url_for
from authlib.integrations.flask_client import OAuth
from src.database.usuarios import Usuario
from src.database import db
from src.domains.configuracao.service import ConfiguracaoService
from src.core.responses import json_success

oauth = OAuth()
bp_oauth = Blueprint("oauth", __name__, url_prefix="/api/auth")

def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

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

    usuario = Usuario.query.filter_by(google_sub=google_sub).first()
    if not usuario:
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario:
            usuario.google_sub = google_sub
            user_dict = usuario.to_dict()
            
            if user_dict["hash_senha"] == None:
                #TODO Lógica de 1° login, usuario existe mas é o 1° log in
                pass
        else:
            return jsonify({"erro": "usuario_nao_cadastrado"}), 403
        db.session.commit()

    if not usuario.ativo:
        session.clear()
        return jsonify({"erro": "conta_inativa"}), 403

    session.permanent = True                    # respeita PERMANENT_SESSION_LIFETIME
    session["usuario_id"] = usuario.id           # chave lida por todos os decorators
    session["tipo_usuario"] = usuario.tipo_usuario
    session["usuario_uuid"] = usuario.uuid       # conveniência para o front-end

    cfg_service = ConfiguracaoService()
    cfg = cfg_service.obter_ou_criar(session["usuario_id"])
    
    return json_success(
        data={"usuario": usuario.to_dict(), "configuracoes": cfg.to_dict()},
        message="Login realizado com sucesso.",
    ),200