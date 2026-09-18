"""
sessaoAutenticacao.py -- Checagem base de sessão e requer_login.

Depende só de sessaoUsuarios.py (getters + _popula_g). Todo decorator
de papel (sessaoPapeis.py) e de senha (sessaoSenha.py) parte da mesma
`_checagem_base_sessao` daqui, então nenhum deles precisa ser
empilhado com `requer_login` -- ver observação no fim do arquivo.
"""

from functools import wraps
from flask import session, jsonify

from src.core.session.sessaoUsuarios import _nao_autenticado, _popula_g


def _checagem_base_sessao():
    """
    Checagens comuns a todo decorator de sessão (autenticação, onboarding,
    mfa). Retorna a resposta de erro se algo falhar, ou None se pode
    prosseguir. Fatorado para não repetir em cada fábrica de decorator.
    """
    if not session.get("id_usuario"):
        return _nao_autenticado()
    if session.get("onboarding_pendente"):
        return jsonify({"erro": "onboarding_pendente"}), 403
    if session.get("mfa_pendente"):
        return jsonify({"erro": "mfa_pendente"}), 401
    return None


def _requer_papeis():
    """
    Fábrica de decorator sem parâmetros -- cobre só a checagem de
    sessão básica (autenticado + onboarding + mfa), usada por
    requer_login. Para exigências de papel, ver requer_admin,
    requer_papel_clinico e requer_admin_ou_papel_clinico em
    sessaoPapeis.py.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            erro = _checagem_base_sessao()
            if erro:
                return erro
            _popula_g()
            return f(*args, **kwargs)
        return wrapper
    return decorator


def requer_login(f):
    """
    Bloqueia qualquer rota clínica/normal a menos que a sessão esteja
    TOTALMENTE liberada: sem onboarding pendente e sem 2FA pendente.

    Também popula g.id_usuario / g.id_empresa / g.is_admin /
    g.funcao_clinica / g.is_super_admin, pra rota não precisar reler a
    sessão manualmente.
    """
    return _requer_papeis()(f)


def ja_logado() -> bool:
    """
    Verifica se o usuário já possui uma sessão ativa

    Retorno:
        200 se já tiver uma sessão
        401 se não tiver uma sessão
    """
    if session.get("id_usuario"):
        return {'authenticated': True}, 200
    return {'authenticated': False}, 401


# ---------------------------------------------------------------------------
# requer_admin, requer_papel_clinico, requer_admin_ou_papel_clinico e
# requer_senha_atualizada (em sessaoPapeis.py / sessaoSenha.py) já
# chamam _checagem_base_sessao() + _popula_g() internamente -- igual
# requer_login. Não é necessário empilhar @requer_login junto com eles;
# empilhar os dois não quebra nada, só é redundante.
# ---------------------------------------------------------------------------