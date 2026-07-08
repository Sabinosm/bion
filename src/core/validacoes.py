import re

# ---------------------------------------------------------------------------
# DDDs válidos no Brasil (Anatel). Usado para rejeitar DDDs inexistentes
# como 00, 10, 20, 23-24, etc, que passariam numa checagem "< 11".
# ---------------------------------------------------------------------------
DDDS_VALIDOS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19,        # SP
    21, 22, 24,                                 # RJ
    27, 28,                                      # ES
    31, 32, 33, 34, 35, 37, 38,                 # MG
    41, 42, 43, 44, 45, 46,                     # PR
    47, 48, 49,                                  # SC
    51, 53, 54, 55,                              # RS
    61,                                           # DF
    62, 64,                                       # GO
    63,                                           # TO
    65, 66,                                       # MT
    67,                                            # MS
    68,                                            # AC
    69,                                            # RO
    71, 73, 74, 75, 77,                          # BA
    79,                                            # SE
    81, 87,                                        # PE
    82,                                             # AL
    83,                                             # PB
    84,                                             # RN
    85, 88,                                         # CE
    86, 89,                                         # PI
    91, 93, 94,                                     # PA
    92, 97,                                         # AM
    95,                                              # RR
    96,                                              # AP
    98, 99,                                          # MA
}


def _limpar_digitos(valor) -> str:
    """Extrai apenas os dígitos de qualquer entrada, tratando None/tipos não-string."""
    if valor is None:
        return ""
    return re.sub(r"\D", "", str(valor))


def validar_cpf(cpf) -> bool:
    """Valida a estrutura e os dígitos verificadores de um CPF."""
    cpf_limpo = _limpar_digitos(cpf)

    if len(cpf_limpo) != 11:
        return False

    # CPFs com todos os dígitos iguais são inválidos apesar de passarem no cálculo
    if cpf_limpo == cpf_limpo[0] * 11:
        return False

    # Primeiro dígito verificador
    soma = sum(int(cpf_limpo[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    digito_1 = resto if resto < 10 else 0
    if digito_1 != int(cpf_limpo[9]):
        return False

    # Segundo dígito verificador
    soma = sum(int(cpf_limpo[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    digito_2 = resto if resto < 10 else 0
    if digito_2 != int(cpf_limpo[10]):
        return False

    return True


def validar_cnpj(cnpj) -> bool:
    """Valida a estrutura e os dígitos verificadores de um CNPJ."""
    cnpj_limpo = _limpar_digitos(cnpj)

    if len(cnpj_limpo) != 14:
        return False

    if cnpj_limpo == cnpj_limpo[0] * 14:
        return False

    pesos_primeiro = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_segundo = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    soma = sum(int(cnpj_limpo[i]) * pesos_primeiro[i] for i in range(12))
    resto = soma % 11
    digito_1 = 0 if resto < 2 else 11 - resto
    if digito_1 != int(cnpj_limpo[12]):
        return False

    soma = sum(int(cnpj_limpo[i]) * pesos_segundo[i] for i in range(13))
    resto = soma % 11
    digito_2 = 0 if resto < 2 else 11 - resto
    if digito_2 != int(cnpj_limpo[13]):
        return False

    return True


def validar_cpf_ou_cnpj(documento) -> bool:
    """Aceita CPF (11 dígitos) ou CNPJ (14 dígitos) — útil quando o campo pode ser qualquer um dos dois."""
    doc_limpo = _limpar_digitos(documento)
    if len(doc_limpo) == 11:
        return validar_cpf(doc_limpo)
    if len(doc_limpo) == 14:
        return validar_cnpj(doc_limpo)
    return False


def validar_telefone_br(telefone) -> bool:
    """
    Valida telefones brasileiros (fixo ou celular), com ou sem máscara.
    Fixo: DDD + 8 dígitos (ex: 3133334444). Celular: DDD + 9 dígitos, começando com 9.
    """
    tel_limpo = _limpar_digitos(telefone)

    if len(tel_limpo) not in (10, 11):
        return False

    ddd = int(tel_limpo[:2])
    if ddd not in DDDS_VALIDOS:
        return False

    # Celular: 11 dígitos, terceiro dígito (primeiro do número) deve ser 9
    if len(tel_limpo) == 11 and tel_limpo[2] != "9":
        return False

    # Fixo: primeiro dígito do número deve ser de 2 a 5 (padrão Anatel para fixos)
    if len(tel_limpo) == 10 and tel_limpo[2] not in "2345":
        return False

    # Rejeita número com todos os dígitos (após o DDD) repetidos, ex: (11) 99999-9999
    numero = tel_limpo[2:]
    if numero == numero[0] * len(numero):
        return False

    return True


def validar_cep(cep) -> bool:
    """Valida se o CEP tem 8 dígitos numéricos e não é uma sequência óbvia inválida."""
    cep_limpo = _limpar_digitos(cep)
    if len(cep_limpo) != 8:
        return False
    if cep_limpo == cep_limpo[0] * 8:
        return False
    return True

def validar_senha(senha: str):
    if not senha:
        return False, {"erro": "senha_obrigatoria"}

    if len(senha) < 12:
        return False, {"erro": "senha_muito_curta"}

    # Limite alto o suficiente para não incomodar ninguém, baixo o
    # suficiente para evitar DoS via hashing de payloads gigantes.
    # Não é limitação do Argon2id (que aceita ~4GB) — é proteção operacional.
    if len(senha) > 128:
        return False, {"erro": "senha_muito_longa"}

    especiais_seguros = set("!@#%^()-_=+[]{}/?~.,:<>'\"|;&$`\\")

    requisitos_faltando = []
    if not any(c.isdigit() for c in senha):
        requisitos_faltando.append("numero")
    if not any(c.isupper() for c in senha):
        requisitos_faltando.append("maiuscula")
    if not any(c in especiais_seguros or not c.isalnum() for c in senha):
        requisitos_faltando.append("caracter_especial")

    if requisitos_faltando:
        return False, {
            "erro": "senha_fraca",
            "requisitos_faltando": requisitos_faltando
        }

    return True, {"success": "senha_forte"}