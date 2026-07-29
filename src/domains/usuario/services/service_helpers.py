"""Funções puras e constantes de apoio ao domínio Usuario.

ALTERADO: monta_atributos_json() e atributos_atuais() trabalhavam com
JSON solto (atributos_profissionais_json). Agora que isso virou a tabela
PapelProfissional, essas funções mudam de "montar/ler JSON" para
"montar/ler dict de campos do papel" — mas os NOMES das funções e o
formato do dict retornado foram mantidos iguais de propósito, para que
quem já chama essas funções precise mudar o mínimo possível.
"""

CAMPOS_SIMPLES_ATUALIZAVEIS = (
    "nome_completo",
    "email",
    "telefone",
    "user_login",
)

# CAMPOS_RESTRITOS_A_ADMIN: as chaves com hífen (numero-crm etc) eram o
# formato do JSON antigo. Mantidas aqui porque o payload de ENTRADA da
# API (o que o cliente HTTP manda) não muda — só a forma de PERSISTIR
# muda. Isso é o núcleo do que discutimos: FHIR/reestruturação interna
# não obriga a mudar contrato de API já em uso pelo front.
CAMPOS_RESTRITOS_A_ADMIN = (
    "tipo_usuario",
    "numero-crm", "uf-crm", "rqe",
    "numero-coren", "uf-coren", "especialidade",
)


def atributos_atuais(u) -> dict:
    """Retorna os atributos profissionais do papel ATIVO do usuário.

    Parâmetros:
        u: instância de Usuario.

    Retorno:
        dict no formato antigo (chaves com hífen), ou {} se não houver
        papel ativo.
    """
    papel = u.papel_ativo()
    if not papel:
        return {}

    if papel.tipo_papel == "medico":
        return {
            "numero-crm": papel.numero_conselho,
            "uf-crm": papel.uf_conselho,
            "rqe": papel.rqe,
        }
    elif papel.tipo_papel == "enfermeiro":
        return {
            "numero-coren": papel.numero_conselho,
            "uf-coren": papel.uf_conselho,
            "especialidade": papel.especialidade,
        }
    return {}


def monta_dados_papel(schema) -> dict | None:
    """Monta um dict pronto para criar/atualizar um PapelProfissional,
    a partir do schema validado.

    Parâmetros:
        schema: instância validada de CadastroUsuarioSchema (ou
            AtualizacaoUsuarioSchema).

    Retorno:
        dict com os campos prontos para PapelProfissional(**dict), ou
        None se o tipo de usuário não exigir papel profissional (admin).
    """
    if schema.tipo_usuario == "medico":
        return {
            "tipo_papel": "medico",
            "numero_conselho": schema.numero_crm,
            "uf_conselho": schema.uf_crm,
            "rqe": (schema.rqe or "").strip() or None,
            "especialidade": None,
        }
    elif schema.tipo_usuario == "enfermeiro":
        return {
            "tipo_papel": "enfermeiro",
            "numero_conselho": schema.numero_coren,
            "uf_conselho": schema.uf_coren,
            "especialidade": schema.especialidade,
            "rqe": None,
        }
    return None

