"""Fixtures compartilhadas por toda a suíte de testes."""

import os
import pytest

os.environ.setdefault("AES_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("HMAC_KEY", "chave-teste-hmac")
os.environ.setdefault("SECRET_KEY", "chave-teste-secret")

from src.main import create_app
from src.models import db as _db


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def empresa(app):
    from src.models.corp.empresa import Empresa
    e = Empresa(nome_fantasia="Hospital Teste", cnpj="00.000.000/0001-00")
    _db.session.add(e)
    _db.session.commit()
    return e


@pytest.fixture()
def usuario_medico(app, empresa):
    from src.models.usuarios import Usuario
    from src.core.security import ph, aes_encrypt, hmac_sha256
    cpf = "111.111.111-11"
    u = Usuario(
        id_empresa=empresa.id, nome_completo="Dr. Fulano", cpf=aes_encrypt(cpf),
        cpf_hash=hmac_sha256(cpf),
        email="medico@teste.com", user_login="medico1", tipo_usuario="medico",
        hash_senha=ph.hash("senha123"),
    )
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def usuario_admin(app, empresa):
    from src.models.usuarios import Usuario
    from src.core.security import ph, aes_encrypt, hmac_sha256
    cpf = "000.000.000-00"
    u = Usuario(
        id_empresa=empresa.id, nome_completo="Admin Geral", cpf=aes_encrypt(cpf),
        cpf_hash=hmac_sha256(cpf),
        email="admin@teste.com", user_login="admin", tipo_usuario="admin",
        hash_senha=ph.hash("senha123"),
    )
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def login_medico(client, usuario_medico):
    client.post("v1/api/auth/login", json={"login": "medico1", "senha": "senha123"})
    return usuario_medico


@pytest.fixture()
def login_admin(client, usuario_admin):
    client.post("v1/api/auth/login", json={"login": "admin", "senha": "senha123"})
    return usuario_admin
