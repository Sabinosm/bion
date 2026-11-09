"""comum.py

Funções compartilhadas pelos controllers do domínio Paciente: montagem do
AutorClinico a partir da sessão (nunca do corpo da requisição), a checagem de função
clínica para exibir PII, leitura do corpo JSON, resposta de erro de negócio (com `erros` por campo) e a variante com a meta
NOOP de auditoria.

O decorator de auditoria não olha o status HTTP, então, sem a meta NOOP, um erro
numa rota auditada seria registrado como acesso com sucesso.
"""

from flask import request

from src.core.exceptions import BionException
from src.core.responses import json_error
from src.core.session import (
    get_funcao_clinica_sessao, get_id_empresa_sessao, get_id_usuario_sessao,
)
from src.domains.atendimento.contexto_clinico_service import AutorClinico


def autor_clinico() -> AutorClinico:
    """AutorClinico da sessão (usuário, função clínica e empresa)."""
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


def pode_ver_clinico() -> bool:
    """True se o usuário da sessão é médico ou enfermeiro (quem vê PII em texto claro)."""
    return get_funcao_clinica_sessao() in ("medico", "enfermeiro")


def corpo_json() -> dict:
    """Corpo JSON da requisição; vazio se ausente. O service rejeita o que não for objeto."""
    return request.get_json(silent=True) or {}


def resposta_erro(ex: BionException):
    """Resposta de erro de negócio: mensagem, status e `erros` por campo da própria exceção."""
    return json_error(ex.message, ex.status_code, erros=ex.erros)


def resposta_erro_noop(ex: BionException):
    """Mesma resposta, com a meta NOOP, para rotas auditadas (o erro não vira acesso com sucesso)."""
    return resposta_erro(ex), {"operacao": "NOOP"}
