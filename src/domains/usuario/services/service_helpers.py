"""Funções puras e constantes de apoio ao domínio Usuario.

Nenhuma função deste módulo acessa banco de dados, sessão ou request:
todas recebem dados e retornam valores, o que facilita testes unitários
isolados do restante da camada de serviço.
"""

import json

from src.schemas.schema_usuario import CadastroUsuarioSchema


CAMPOS_SIMPLES_ATUALIZAVEIS = (
    "nome_completo",
    "email",
    "telefone",
    "user_login",
)

CAMPOS_RESTRITOS_A_ADMIN = (
    "tipo_usuario",
    "numero-crm", "uf-crm", "rqe",
    "numero-coren", "uf-coren", "especialidade",
)


def atributos_atuais(u) -> dict:
    """Decodifica o JSON de atributos profissionais salvo no usuário.

    Parâmetros:
        u: instância de Usuario contendo o campo `atributos_profissionais_json`.

    Retorno:
        dict com os atributos decodificados, ou `{}` se o campo estiver
        vazio ou contiver um JSON inválido.
    """
    if not u.atributos_profissionais_json:
        return {}
    try:
        return json.loads(u.atributos_profissionais_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def monta_atributos_json(schema: CadastroUsuarioSchema):
    """Monta o JSON de atributos profissionais a partir do schema validado.

    O conjunto de campos incluídos depende de `schema.tipo_usuario`:
    médico usa CRM/UF/RQE; enfermeiro usa COREN/UF/especialidade.

    Parâmetros:
        schema: instância validada de CadastroUsuarioSchema.

    Retorno:
        str contendo o JSON serializado, ou None se o tipo de usuário
        não exigir atributos profissionais.
    """
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