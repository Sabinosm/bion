

from flask import Flask, app, jsonify
from flask_cors import CORS

from src.config.database import config
from src.models import db, migrate
from src.core.exceptions import BionException


def create_app(config_name: str = "development") -> Flask:
    from src.domains.auth.oauth import init_oauth
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    _registrar_blueprints(app)
    _registrar_error_handlers(app)

    origens_permitidas = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    ]

    CORS(
    app,
    resources={r"/v1/api/*": {"origins": origens_permitidas}},
    supports_credentials=True,
    )
    init_oauth(app)
    
    return app


def _registrar_blueprints(app: Flask):
    from src.domains.auth.controllers import bp as auth_bp
    from src.domains.usuario.controller import bp as usuario_bp
    from src.domains.empresa.controller import bp as empresa_bp
    from src.domains.regiao.controller import bp as regiao_bp
    from src.domains.configuracao.controller import bp as configuracao_bp
    from src.domains.catalogo.controller import bp_exames as catalogo_exames_bp
    from src.domains.catalogo.controller import bp_medicamentos as catalogo_medicamentos_bp
    from src.domains.protocolos_ia.controller import bp_protocolo as protocolo_bp
    from src.domains.protocolos_ia.controller import bp_ia as ia_bp
    from src.domains.consulta.controller import bp_consulta as consulta_bp
    from src.domains.atendimento.controller import bp_atendimento as atendimento_bp
    from src.domains.prescricao.controller import bp_prescricao as prescricao_bp
    from src.domains.auditoria.controller import bp as auditoria_bp
    from src.domains.dados_clinicos.controller import bp_dados_clinicos
    from src.domains.paciente.controllers import pessoal_bp, clinico_bp, lgpd_bp
    from src.domains.auth.oauth import bp_oauth
    from src.domains.auth.onboarding import bp_onboarding
    from src.domains.auth.step_up import bp_step_up
    from src.domains.auth.webauthn_2fa import bp_webauthn_2fa
    from src.domains.auth.status import bp_status

    app.register_blueprint(auth_bp, url_prefix="/v1/api/auth")       
    app.register_blueprint(bp_status, url_prefix="/v1/api/auth")                                       # /v1/api/authc
    app.register_blueprint(bp_oauth, url_prefix="/v1/api/auth")
    app.register_blueprint(bp_onboarding, url_prefix="/v1/api/auth")
    app.register_blueprint(bp_step_up, url_prefix="/v1/api")
    app.register_blueprint(bp_webauthn_2fa, url_prefix="/v1/api")
    app.register_blueprint(bp_dados_clinicos, url_prefix="/v1/api/dadosClinicos")    
    app.register_blueprint(usuario_bp, url_prefix="/v1/api/usuarios")
    app.register_blueprint(empresa_bp, url_prefix="/v1/api/empresas")
    app.register_blueprint(regiao_bp, url_prefix="/v1/api/regioes")
    app.register_blueprint(configuracao_bp, url_prefix="/v1/api/configuracoes")
    app.register_blueprint(catalogo_exames_bp, url_prefix="/v1/api/catalogo/exames")
    app.register_blueprint(catalogo_medicamentos_bp, url_prefix="/v1/api/catalogo/medicamentos")
    app.register_blueprint(protocolo_bp, url_prefix="/v1/api/protocolos")
    app.register_blueprint(ia_bp, url_prefix="/v1/api/ia")
    app.register_blueprint(consulta_bp, url_prefix="/v1/api/consultas")
    app.register_blueprint(atendimento_bp, url_prefix="/v1/api/atendimentos")
    app.register_blueprint(prescricao_bp, url_prefix="/v1/api/prescricoes")
    app.register_blueprint(auditoria_bp, url_prefix="/v1/api/auditoria")
    app.register_blueprint(pessoal_bp, url_prefix="/v1/api/pacientes")
    app.register_blueprint(clinico_bp, url_prefix="/v1/api/pacientes")
    app.register_blueprint(lgpd_bp, url_prefix="/v1/api/pacientes")

    @app.get("/v1/api/health")
    def health():
        return jsonify({"status": "success", "message": "Bion API no ar."})


def _registrar_error_handlers(app: Flask):
    @app.errorhandler(BionException)
    def handle_bion_exception(err: BionException):
        return jsonify({"status": "error", "message": err.message}), err.status_code

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify({"status": "error", "message": "Recurso não encontrado."}), 404

    @app.errorhandler(405)
    def handle_405(err):
        return jsonify({"status": "error", "message": "Método não permitido."}), 405

    @app.errorhandler(500)
    def handle_500(err):
        db.session.rollback()
        return jsonify({"status": "error", "message": "Erro interno do servidor."}), 500
