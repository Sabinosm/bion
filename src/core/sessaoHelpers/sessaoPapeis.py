"""
sessaoPapeis.py -- Decorators de autorização por papel (is_admin /
funcao_clinica), incluindo requer_super_admin.

Cada decorator aqui já inclui a checagem COMPLETA de sessão
(autenticado + onboarding concluído + mfa concluído -- igual
requer_login, definido em sessaoAutenticacao.py), então não é
necessário empilhar @requer_login junto: um decorator sozinho já
garante tudo. Empilhar os dois juntos não quebra nada, só é redundante.

Atenção: empilhar @requer_admin com @requer_papel_clinico(...) exige
as DUAS condições (AND) -- use requer_admin_ou_papel_clinico(...)
quando a intenção é liberar para qualquer um dos dois (OR).
"""

from functools import wraps
from flask import session

from src.core.sessaoHelpers.sessaoUsuarios import (
    get_is_admin_sessao,
    get_funcao_clinica_sessao,
    _sem_permissao,
    _popula_g,
)
from src.core.sessaoHelpers.sessaoAutenticacao import _checagem_base_sessao


def requer_admin(f):
    """
    Bloqueia a rota a menos que o usuário logado tenha is_admin=True.

    Não depende de funcao_clinica -- um admin com ou sem papel clínico
    associado passa igualmente por este decorator.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        erro = _checagem_base_sessao()
        if erro:
            return erro
        if not get_is_admin_sessao():
            return _sem_permissao("administrador")
        _popula_g()
        return f(*args, **kwargs)
    return wrapper


def requer_papel_clinico(*papeis_permitidos):
    """
    Bloqueia a rota a menos que a função clínica do usuário logado
    esteja entre papeis_permitidos ("medico", "enfermeiro").

    Não depende de is_admin -- um médico que também é admin passa
    igualmente por este decorator, contanto que tenha o papel clínico.

    Uso:
        @requer_papel_clinico("medico")
        @requer_papel_clinico("medico", "enfermeiro")
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            erro = _checagem_base_sessao()
            if erro:
                return erro
            if get_funcao_clinica_sessao() not in papeis_permitidos:
                rotulo = " ou ".join(papeis_permitidos)
                return _sem_permissao(rotulo)
            _popula_g()
            return f(*args, **kwargs)
        return wrapper
    return decorator


def requer_admin_ou_papel_clinico(*papeis_clinicos_permitidos):
    """
    Libera a rota se o usuário for admin (is_admin=True) OU tiver uma
    das funções clínicas em papeis_clinicos_permitidos -- OR, não AND.

    Existe porque simplesmente empilhar @requer_admin com
    @requer_papel_clinico(...) exigiria as DUAS condições ao mesmo
    tempo (mais restritivo que o pretendido). Use esta fábrica quando
    a rota deve liberar para qualquer um dos dois (ex: admin ou médico).

    Uso:
        @requer_admin_ou_papel_clinico("medico")
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            erro = _checagem_base_sessao()
            if erro:
                return erro
            is_admin = get_is_admin_sessao()
            papel_ok = get_funcao_clinica_sessao() in papeis_clinicos_permitidos
            if not (is_admin or papel_ok):
                rotulo = " ou ".join(("administrador",) + papeis_clinicos_permitidos)
                return _sem_permissao(rotulo)
            _popula_g()
            return f(*args, **kwargs)
        return wrapper
    return decorator


def requer_super_admin(f):
    """
    Bloqueia a rota a menos que o usuário logado seja o super admin da
    empresa (o admin fundador -- ver Usuario.is_super_admin).

    Já inclui a checagem completa de sessão (autenticado + onboarding +
    mfa), igual requer_admin -- não precisa empilhar com @requer_login
    nem com @requer_admin.

    Use isto quando a exigência é binária pra rota inteira (ex: criar
    um novo admin). Quando a checagem depende do ALVO da operação (ex:
    atualizar/desativar um usuário que pode ou não ser admin), use
    @requer_admin na rota e faça a checagem fina dentro do service com
    g.is_super_admin -- um decorator não tem acesso ao alvo antes da
    rota rodar.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        erro = _checagem_base_sessao()
        if erro:
            return erro

        if not session.get("is_admin") or not session.get("is_super_admin"):
            return _sem_permissao("administrador principal")

        _popula_g()
        from flask import g
        g.is_super_admin = True

        return f(*args, **kwargs)
    return wrapper