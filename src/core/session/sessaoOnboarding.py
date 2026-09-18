"""
sessaoOnboarding.py -- Decorators usados nas rotas de onboarding
(definir senha, cadastrar WebAuthn) e no caso híbrido de rotas que
liberam tanto sessão completa quanto onboarding em andamento.
"""

from functools import wraps
from flask import session, jsonify

from src.core.session.sessaoAutenticacao import _checagem_base_sessao
from src.core.session.sessaoUsuarios import _popula_g


def onboarding_pendente_required(f):
    """Usado só nas rotas de onboarding (definir senha, cadastrar WebAuthn)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("onboarding_pendente"):
            return jsonify({"erro": "sessao_invalida"}), 401
        return f(*args, **kwargs)
    return wrapper


def requer_login_ou_onboarding_pendente(f):
    """Libera a rota se a sessão tiver `id_usuario` E (sessão totalmente
    completa OU `onboarding_pendente=True`).

    Ramo onboarding_pendente: não passa por `_checagem_base_sessao()`
    (que rejeitaria justamente por onboarding_pendente=True) nem por
    `_popula_g()` (que exigiria dados -- id_empresa, is_admin, etc --
    que ainda não existem na sessão nesse ponto). Só confirma
    `id_usuario` e segue. Rotas que usam este decorator devem obter o
    usuário via `get_usuario_sessao()`/`get_id_usuario_sessao()`, não
    via `g.id_empresa` (que não existe neste ramo).

    Ramo sessão completa: delega para `_checagem_base_sessao()` e
    `_popula_g()`, mesma checagem de `requer_login` -- reaproveitados
    em vez de duplicados, para não divergir se esses helpers mudarem.

    NÃO inclui a checagem de `requer_senha_atualizada` -- esse
    decorator é para LEITURA de dados clínicos sensíveis, um caso de
    uso diferente do cadastro de 2FA; se algum dia cadastro de 2FA
    precisar dessa checagem também, aplicar via decorator empilhado
    na rota específica, não aqui.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario"):
            return jsonify({"erro": "sessao_invalida"}), 401

        if session.get("onboarding_pendente"):
            # Onboarding em andamento -- sessão ainda não está
            # completa, _popula_g() não se aplica aqui.
            return f(*args, **kwargs)

        # Sessão completa -- mesma checagem de requer_login (via
        # _checagem_base_sessao, importada de sessaoAutenticacao).
        erro = _checagem_base_sessao()
        if erro:
            return erro
        _popula_g()
        return f(*args, **kwargs)
    return wrapper