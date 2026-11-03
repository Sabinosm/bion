"""prescricao_controller_helpers.py

Funções compartilhadas pelos controllers do domínio de prescrição (medicamentos,
exames e resultado): leitura do corpo JSON e conversão de erros em resposta de
erro com a meta de auditoria NOOP. O decorator de auditoria não olha o status
HTTP, então, sem o NOOP, um erro seria registrado como acesso com sucesso.

O erro de validação do schema devolve duas coisas: `message` com o texto curto
de sempre (campo: mensagem; ...) e `erros` com {campo: mensagem}, para o front
pintar o input certo sem interpretar o texto.
"""

from flask import request
from pydantic import ValidationError

from src.core.erros_pydantic import erros_pydantic_por_campo
from src.core.exceptions import BionException
from src.core.responses import json_error
from src.domains.auditoria.auditoria_helpers_service import erro

from .schema_prescricoes import formatar_erros_pydantic


def corpo_json() -> dict:
    """Corpo JSON da requisição; vazio se ausente. O schema rejeita o que não for objeto."""
    return request.get_json(silent=True) or {}


def erro_validacao(ex: ValidationError):
    """Resposta 422 com `erros` por campo, mais a meta NOOP de auditoria."""
    return erro(json_error(formatar_erros_pydantic(ex), 422, erros=erros_pydantic_por_campo(ex)))


def erro_bion(ex: BionException):
    """Resposta de erro de negócio (status e `erros` da própria exceção), mais a meta NOOP."""
    return erro(json_error(ex.message, ex.status_code, erros=ex.erros))
