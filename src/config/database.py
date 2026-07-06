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
from sqlalchemy import create_engine

# 1. Carrega as variáveis do ficheiro .env
load_dotenv()

# 2. Captura os dados do banco principal
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
database = os.getenv("DB_NAME")

# 3. Monta a URL padrão do MySQL
DATABASE_URL_DEFAULT = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

# 4. Cria o engine para testes rápidos de conexão, se necessário
engine = create_engine(DATABASE_URL_DEFAULT)


class Config:
    """Configuração Base"""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-troque")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessão / Cookie
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_PERMANENT = True
    SESSION_COOKIE_HTTPONLY = True   # JS do front não acessa o cookie
    SESSION_COOKIE_SAMESITE = "Lax"  # Proteção CSRF básica # ou "None" se front e back tiverem domínios diferentes
         
    
    GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
    
    # JSON
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    """Ambiente de Desenvolvimento (Local)"""
    DEBUG = True
    # Usa a string montada pelo .env. Se falhar, tenta o fallback local do MySQL
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", 
        DATABASE_URL_DEFAULT )


class ProductionConfig(Config):
    """Ambiente de Produção (Servidor)"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", DATABASE_URL_DEFAULT)
    
    # Segurança de produção ativa
    SESSION_COOKIE_SECURE = False # Cookie só trafega via HTTPS # True obrigatório se SAMESITE="None", mas exige HTTP


class TestingConfig(Config):
    """Ambiente de Testes Automatizados"""
    TESTING = True
    # Aponta para uma base MySQL separada de testes para não apagar seus dados reais
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "mysql+pymysql://root:root@localhost:3306/bion_test")
    WTF_CSRF_ENABLED = False


# Dicionário de mapeamento dos ambientes
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}   