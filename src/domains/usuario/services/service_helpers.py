"""Funções puras e constantes de apoio ao domínio Usuario."""

CAMPOS_SIMPLES_ATUALIZAVEIS = (
    "nome_completo",
    "email",
    "telefone",
    "user_login",
)

# As chaves com hífen (numero-crm etc) são o formato do payload de
# ENTRADA da API, mantido por compatibilidade com o front. is_admin e
# tipo_papel são os dois eixos ortogonais de permissão/registro
# profissional, ambos restritos a admin.
CAMPOS_RESTRITOS_A_ADMIN = (
    "is_admin",
    "tipo_papel",
    "numero-crm", "uf-crm", "rqe",
    "numero-coren", "uf-coren", "especialidade",
)


def atributos_atuais(u) -> dict:
    """Retorna os atributos profissionais do papel ATIVO do usuário.

    Parâmetros:
        u: instância de Usuario.

    Retorno:
        dict no formato de payload (chaves com hífen), ou {} se não
        houver papel ativo.
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
        None se tipo_papel for None (usuário sem função clínica,
        tipicamente admin puro).
    """
    if schema.tipo_papel == "medico":
        return {
            "tipo_papel": "medico",
            "numero_conselho": schema.numero_crm,
            "uf_conselho": schema.uf_crm,
            "rqe": (schema.rqe or "").strip() or None,
            "especialidade": None,
        }
    elif schema.tipo_papel == "enfermeiro":
        return {
            "tipo_papel": "enfermeiro",
            "numero_conselho": schema.numero_coren,
            "uf_conselho": schema.uf_coren,
            "especialidade": schema.especialidade,
            "rqe": None,
        }
    return None