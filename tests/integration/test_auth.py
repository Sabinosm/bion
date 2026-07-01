"""
Testes de integracao do fluxo de autenticacao.

Cobrem especificamente a regressao do bug de sessao: o controller
original gravava session["usuario_uuid"] mas os decorators liam
session.get("usuario_id"), entao requer_login sempre falhava mesmo
apos login bem-sucedido.
"""


def test_login_com_credenciais_corretas(client, usuario_medico):
    resp = client.post("/api/auth/login", json={"login": "medico1", "senha": "senha123"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert body["data"]["usuario"]["user_login"] == "medico1"


def test_login_com_senha_incorreta(client, usuario_medico):
    resp = client.post("/api/auth/login", json={"login": "medico1", "senha": "errada"})
    assert resp.status_code == 401


def test_rota_protegida_sem_login_retorna_401(client):
    resp = client.get("/api/usuarios/")
    assert resp.status_code == 401


def test_rota_protegida_apos_login_funciona(client, login_admin):
    """Regressão do bug principal: antes da correção, esta chamada
    retornava 401 mesmo com login bem-sucedido, porque a sessão gravava
    a chave errada."""
    resp = client.get("/api/usuarios/")
    assert resp.status_code == 200


def test_me_reflete_sessao_ativa(client, login_medico):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["usuario"]["tipo_usuario"] == "medico"


def test_logout_encerra_sessao(client, login_medico):
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_decorator_de_papel_bloqueia_tipo_errado(client, login_medico):
    """requer_admin deve bloquear um usuário logado como médico."""
    resp = client.post("/api/empresas/", json={"nome_fantasia": "X", "cnpj": "1"})
    assert resp.status_code == 403
