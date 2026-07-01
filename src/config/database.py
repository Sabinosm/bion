"""
Configurações globais do Bion: banco de dados, sessão, segredos via .env.

A API mantém autenticação por cookie de sessão httpOnly (em vez de JWT),
porque é servida no mesmo domínio do front-end (SPA same-site) — decisão
confirmada com o time. CORS, se necessário para outro domínio de front,
deve ser configurado com `supports_credentials=True` e origem explícita
(nunca "*", pois cookies exigem origem nomeada).
"""

import os
from datetime import timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
database = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

engine = create_engine(DATABASE_URL)

# Teste rápido de conexão
with engine.connect() as conexao:
    print("Conexão estabelecida com sucesso e de forma segura!")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-troque")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessão / cookie
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_PERMANENT = True
    SESSION_COOKIE_HTTPONLY = True   # JS do front não acessa o cookie
    SESSION_COOKIE_SAMESITE = "Lax"  # proteção CSRF básica

    # JSON
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:root@localhost:3306/bion_dev"
    )


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    # Cookie só trafega em HTTPS em produção. (No bion.zip original este
    # valor estava como False em ProductionConfig, o que anulava a proteção
    # do cookie mesmo servindo a aplicação via HTTPS — corrigido para True.)
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
