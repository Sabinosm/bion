"""
Helpers e constantes do dominio Usuario.

Extraido de service.py para reduzir o tamanho do arquivo principal.
Contem apenas funcoes puras de apoio ao merge/validacao de atributos
profissionais -- nenhuma delas acessa banco, sessao ou request.
"""

import json

from ...schemas.schema_usuario import CadastroUsuarioSchema


CAMPOS_SIMPLES_ATUALIZAVEIS = (
    "nome_completo",
    "email",
    "telefone",
    "user_login",
)

# Só admin pode alterar isso, mesmo no próprio cadastro
CAMPOS_RESTRITOS_A_ADMIN = (
    "tipo_usuario",
    "numero-crm", "uf-crm", "rqe",
    "numero-coren", "uf-coren", "especialidade",
)


def atributos_atuais(u) -> dict:
    """Decodifica o JSON de atributos profissionais salvo no banco.
    Sem isso, o merge de 'dados atuais' fica sempre vazio."""
    if not u.atributos_profissionais_json:
        return {}
    try:
        return json.loads(u.atributos_profissionais_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def monta_atributos_json(schema: CadastroUsuarioSchema):
    atributos_dict = {}
    if schema.tipo_usuario == "medico":
        atributos_dict = {
            "numero-crm": schema.numero_crm,
            "uf-crm": schema.uf_crm,
            "rqe": (schema.rqe or "").strip(),
        }
    elif schema.tipo_usuario == "enfermeiro":
        atributos_dict = {
            "numero-coren": schema.numero_coren,
            "uf-coren": schema.uf_coren,
            "especialidade": schema.especialidade,
        }
    return json.dumps(atributos_dict) if atributos_dict else None