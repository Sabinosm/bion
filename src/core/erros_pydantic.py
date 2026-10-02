"""Helper compartilhado: erros do Pydantic em formato estruturado.

Complementa erros_pydantic_por_campo (schema_usuario.py), que devolve
uma string única. Aqui o resultado é {campo: mensagem}, para ir em
BionException(erros=...) e daí no corpo de json_error, permitindo que o
front pinte o input certo sem interpretar texto.

Sugestão de caminho: src/core/erros_pydantic.py
"""

from pydantic import ValidationError


def erros_pydantic_por_campo(exc: ValidationError, campo_geral: str = "_geral") -> dict:
    """Converte ValidationError em {campo: mensagem}.

    - Remove o prefixo "Value error, " que o Pydantic v2 põe nas
      mensagens de ValueError levantado em validators.
    - Erros sem campo (model_validator, loc vazio) vão para `campo_geral`
      ("_geral" por padrão; o front trata essa chave como mensagem geral).
    - Mantém só o primeiro erro de cada campo.
    """
    erros = {}
    for erro in exc.errors():
        campo = ".".join(str(p) for p in erro["loc"]) or campo_geral
        msg = erro["msg"].removeprefix("Value error, ")
        erros.setdefault(campo, msg)
    return erros
