"""
Testes de integracao do fluxo clinico completo: cadastro de paciente com
PII cifrada, abertura de consulta, triagem, execucao de protocolo via IA
e a rota output-triagem (regressao do bug de metodo faltante).
"""

import pytest
from datetime import date


def _cadastrar_paciente(client):
    return client.post("/api/pacientes/", json={
        "sexo_biologico": "M", "data_nascimento": "1990-05-10",
        "nome_completo": "João da Silva", "cpf": "222.222.222-22",
        "telefone": "11999999999", "email": "joao@teste.com",
    })


def test_cadastro_paciente_cifra_pii_no_banco(app, client, login_medico):
    from src.database import db as _db
    from src.database.paciente import PacientePessoal

    resp = _cadastrar_paciente(client)
    assert resp.status_code == 201

    with app.app_context():
        pessoal = PacientePessoal.query.first()
        # o CPF em texto claro não deve estar salvo diretamente no banco
        assert "222.222.222-22" not in pessoal.cpf
        assert "João da Silva" not in pessoal.nome_completo


def test_medico_ve_pii_descriptografada(client, login_medico):
    resp = _cadastrar_paciente(client)
    uuid = resp.get_json()["data"]["uuid"]

    resp = client.get(f"/api/pacientes/{uuid}")
    pessoal = resp.get_json()["data"]["pessoal"]
    assert pessoal["nome_completo"] == "João da Silva"
    assert pessoal["cpf"] == "222.222.222-22"


def test_cpf_duplicado_gera_conflito(client, login_medico):
    _cadastrar_paciente(client)
    resp = _cadastrar_paciente(client)
    assert resp.status_code == 409


def test_fluxo_triagem_mts_ate_output(app, client, login_medico):
    """Fluxo completo via API: paciente -> consulta -> triagem ->
    coleta clínica -> input de protocolo -> execução IA (MTS) ->
    consulta do resultado pela tela médica (output-triagem)."""
    from src.database import db as _db
    from src.database.protocolos import ProtocoloCatalogo

    with app.app_context():
        p = ProtocoloCatalogo(
            nome_protocolo="Manchester Triage System", sigla="MTS",
            tipo_resultado="categoria-cor", versao_vigente="3ed",
            data_vigencia=date(2014, 1, 1), escopo_uso="triagem",
        )
        _db.session.add(p)
        _db.session.commit()

    r = _cadastrar_paciente(client)
    paciente_uuid = r.get_json()["data"]["uuid"]

    r = client.post(f"/api/consultas/paciente/{paciente_uuid}", json={"tipo_consulta": "triagem"})
    assert r.status_code == 201
    consulta_uuid = r.get_json()["data"]["uuid"]

    r = client.post(f"/api/atendimentos/consulta/{consulta_uuid}/abrir-triagem")
    assert r.status_code == 201
    atendimento_uuid = r.get_json()["data"]["uuid"]

    r = client.post(f"/api/atendimentos/{atendimento_uuid}/coleta-clinica",
                     json={"desde_quando_sintomas": 2})
    assert r.status_code == 201
    coleta_uuid = r.get_json()["data"]["uuid"]

    r = client.post(f"/api/atendimentos/coleta-clinica/{coleta_uuid}/input-protocolo", json={
        "queixa_principal": "dor no peito",
        "input_json": {"fluxograma": {"discriminadores": [
            {"nome": "dor toracica", "resultado": "positivo", "cor_resultante": "Vermelho"}
        ]}},
    })
    assert r.status_code == 201
    input_uuid = r.get_json()["data"]["uuid"]

    with app.app_context():
        from src.database.clinico import InputProtocolo
        id_input = InputProtocolo.query.filter_by(uuid=input_uuid).first().id

    r = client.post("/api/ia/analisar", json={
        "sigla_protocolo": "MTS", "id_input_protocolo": id_input,
        "queixa_principal": "dor no peito",
        "input_json": {"fluxograma": {"discriminadores": [
            {"nome": "dor toracica", "resultado": "positivo", "cor_resultante": "Vermelho"}
        ]}},
    })
    assert r.status_code == 201
    assert r.get_json()["data"]["output_ia"]["cor_mts"] == "Vermelho"

    # Regressão do bug: esta rota quebrava com AttributeError
    # (OutputBionService.buscar_output_triagem não existia).
    r = client.get(f"/api/ia/output-triagem/{consulta_uuid}")
    assert r.status_code == 200
    assert r.get_json()["data"]["cor_mts"] == "Vermelho"


def test_encerrar_consulta_com_desfecho_invalido(app, client, login_medico):
    r = _cadastrar_paciente(client)
    paciente_uuid = r.get_json()["data"]["uuid"]
    r = client.post(f"/api/consultas/paciente/{paciente_uuid}", json={"tipo_consulta": "triagem"})
    consulta_uuid = r.get_json()["data"]["uuid"]

    r = client.post(f"/api/consultas/{consulta_uuid}/encerrar", json={"desfecho_final": "invalido"})
    assert r.status_code == 422


def test_anonimizacao_requer_admin(app, client, login_medico):
    r = _cadastrar_paciente(client)
    paciente_uuid = r.get_json()["data"]["uuid"]
    r = client.post(f"/api/pacientes/{paciente_uuid}/anonimizar")
    assert r.status_code == 403


def test_anonimizacao_remove_pii(app, client, login_admin):
    from src.database.usuarios import Usuario
    from src.core.security import ph, aes_encrypt, hmac_sha256
    from src.database import db as _db

    with app.app_context():
        medico = Usuario.query.filter_by(user_login="admin").first()
        # criamos um médico auxiliar só para cadastrar o paciente
        cpf = "333.333.333-33"
        m = Usuario(id_empresa=medico.id_empresa, nome_completo="Dra. Ciclana",
                     cpf=aes_encrypt(cpf), cpf_hash=hmac_sha256(cpf), email="ciclana@teste.com",
                     user_login="medico2", tipo_usuario="medico", hash_senha=ph.hash("senha123"))
        _db.session.add(m)
        _db.session.commit()

    client.post("/api/auth/login", json={"login": "medico2", "senha": "senha123"})
    r = _cadastrar_paciente(client)
    paciente_uuid = r.get_json()["data"]["uuid"]

    client.post("/api/auth/login", json={"login": "admin", "senha": "senha123"})
    r = client.post(f"/api/pacientes/{paciente_uuid}/anonimizar")
    assert r.status_code == 200

    r = client.get(f"/api/pacientes/{paciente_uuid}")
    assert r.get_json()["data"].get("pessoal") is None
