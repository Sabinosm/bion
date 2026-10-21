"""
sessaoAutenticacao.py

Checagem base de sessão e o decorator de login. Aqui está o núcleo que todos os
decorators de papel (sessaoPapeis.py) e de senha (sessaoSenha.py) reaproveitam:
verificar se há usuário na sessão, se o onboarding terminou, se o segundo
fator foi confirmado e se a sessão tem empresa, e só então liberar a rota,
preenchendo o `g` com os dados da sessão. Nas rotas que pedem, os privilégios
gravados na sessão são revalidados contra o banco antes da checagem de papel
(ver sessaoPrivilegios.py).

Como cada um desses decorators já faz a checagem completa sozinho, nenhum
precisa ser empilhado com o de login. Empilhar os dois não quebra nada, só é
redundante.

Depende de sessaoUsuarios.py e sessaoPrivilegios.py.
"""

from functools import wraps
from typing import Callable, Optional

from flask import session

from src.core.session.sessaoUsuarios import (
    _nao_autenticado,
    _popula_g,
    _resposta_erro,
    get_id_empresa_sessao,
)
from src.core.session.sessaoPrivilegios import revalidar_privilegios


def _checagem_base_sessao():
    """Checagens comuns a todo decorator de sessão liberada.

    Devolve a resposta de bloqueio se a sessão não estiver liberada, ou None se
    a rota pode prosseguir. Em ordem:
      - sem `id_usuario`: 401 `nao_autenticado`;
      - `onboarding_pendente`: 403 `onboarding_pendente`;
      - `mfa_pendente`: 401 `mfa_pendente`;
      - sem `id_empresa` na sessão: a sessão é encerrada e responde 401
        `sessao_invalida`.
    """
    if not session.get("id_usuario"):
        return _nao_autenticado()
    if session.get("onboarding_pendente"):
        return _resposta_erro("onboarding_pendente", "Conclua o cadastro para continuar.", 403)
    if session.get("mfa_pendente"):
        return _resposta_erro("mfa_pendente", "Confirme o segundo fator para continuar.", 401)
    if not get_id_empresa_sessao():
        session.clear()
        return _resposta_erro("sessao_invalida", "Sessão inválida. Faça login novamente.", 401)
    return None


def _requer_papeis(
    verificar_permissao: Optional[Callable[[], Optional[tuple]]] = None,
    revalidar: bool = False,
):
    """Fábrica de decorator: sessão básica, revalidação opcional, permissão opcional e preenchimento do `g`.

    A ordem é sempre a mesma: checagem base de sessão, revalidação dos
    privilégios contra o banco (se pedida), a permissão (se houver), depois
    `_popula_g()` e só então a view.

    Args:
        verificar_permissao: função sem argumentos que devolve a resposta de
            erro se o usuário não tiver a permissão exigida, ou None se tiver.
            Sem ela, só a sessão é checada (caso do login comum).
        revalidar: se True, relê o usuário do banco antes da checagem de papel
            (ver sessaoPrivilegios.py), de modo que um papel retirado ou um
            usuário desativado deixam de valer na hora, e não só no fim da
            sessão. Custa uma consulta por requisição nessa rota.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            erro = _checagem_base_sessao()
            if not erro and revalidar:
                erro = revalidar_privilegios()
            if not erro and verificar_permissao:
                erro = verificar_permissao()
            if erro:
                return erro
            _popula_g()
            return f(*args, **kwargs)
        return wrapper
    return decorator


def requer_login(f):
    """Bloqueia a rota a menos que a sessão esteja TOTALMENTE liberada.

    Totalmente liberada significa sem onboarding pendente e sem 2FA pendente.
    Também popula `g.id_usuario`, `g.uuid_usuario`, `g.id_empresa`,
    `g.is_admin`, `g.funcao_clinica` e `g.is_super_admin`, para a rota não
    precisar reler a sessão.
    """
    return _requer_papeis()(f)


def ja_logado() -> tuple:
    """Informa se existe uma sessão iniciada, para uso direto como retorno de rota.

    Confere `id_usuario` e o onboarding: uma sessão com onboarding pendente
    conta como NÃO iniciada. Uma sessão com 2FA pendente continua contando como
    iniciada, porque é um estado frequente e é o frontend que decide para onde
    encaminhá-la.

    Returns:
        ({"authenticated": True}, 200) se houver sessão iniciada, ou
        ({"authenticated": False}, 401) se não houver ou se o onboarding
        estiver pendente.
    """
    if session.get("id_usuario") and not session.get("onboarding_pendente"):
        return {"authenticated": True}, 200
    return {"authenticated": False}, 401