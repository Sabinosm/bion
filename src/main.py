

from flask import Flask, app, jsonify
from flask_cors import CORS

from src.config.database import config
from src.database import db, migrate
from src.core.exceptions import BionException


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    _registrar_blueprints(app)
    _registrar_error_handlers(app)

    origens_permitidas = [
        "http://127.0.0.1:5500",  
        "http://localhost:5500",             
        "http://127.0.0.1:5500"
    ]

    CORS(app, resources={r"/api/*": {"origins": origens_permitidas}})

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
    from src.domains.atendimento.controller import bp_consulta as consulta_bp
    from src.domains.atendimento.controller import bp_atendimento as atendimento_bp
    from src.domains.atendimento.controller import bp_prescricao as prescricao_bp
    from src.domains.auditoria.controller import bp as auditoria_bp
    from src.domains.paciente.controllers import pessoal_bp, clinico_bp, lgpd_bp

    app.register_blueprint(auth_bp)                                        # /api/authc
    app.register_blueprint(usuario_bp, url_prefix="/api/usuarios")
    app.register_blueprint(empresa_bp, url_prefix="/api/empresas")
    app.register_blueprint(regiao_bp, url_prefix="/api/regioes")
    app.register_blueprint(configuracao_bp, url_prefix="/api/configuracao")
    app.register_blueprint(catalogo_exames_bp, url_prefix="/api/catalogo/exames")
    app.register_blueprint(catalogo_medicamentos_bp, url_prefix="/api/catalogo/medicamentos")
    app.register_blueprint(protocolo_bp, url_prefix="/api/protocolos")
    app.register_blueprint(ia_bp, url_prefix="/api/ia")
    app.register_blueprint(consulta_bp, url_prefix="/api/consultas")
    app.register_blueprint(atendimento_bp, url_prefix="/api/atendimentos")
    app.register_blueprint(prescricao_bp, url_prefix="/api/prescricoes")
    app.register_blueprint(auditoria_bp, url_prefix="/api/auditoria")
    app.register_blueprint(pessoal_bp, url_prefix="/api/pacientes")
    app.register_blueprint(clinico_bp, url_prefix="/api/pacientes")
    app.register_blueprint(lgpd_bp, url_prefix="/api/pacientes")

    @app.get("/api/health")
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
