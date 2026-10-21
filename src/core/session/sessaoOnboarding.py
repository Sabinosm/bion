"""
sessaoOnboarding.py

Decorators das rotas que atendem uma sessão em onboarding: as exclusivas do
onboarding (definir senha, consultar o estado do 2FA, concluir) e as híbridas,
que servem tanto a quem está com a sessão completa quanto a quem ainda está
no meio do onboarding (o cadastro de WebAuthn e de TOTP, que acontece no
primeiro acesso e depois nas configurações da conta).

Uma sessão em onboarding ainda não está completa: faltam dados como
`id_empresa` e os privilégios de papel, então esses decorators não preenchem o
`g` nesse estado.
"""

from functools import wraps

from flask import session

from src.core.session.sessaoAutenticacao import _checagem_base_sessao
from src.core.session.sessaoUsuarios import _popula_g, _resposta_erro


def onboarding_pendente_required(f):
    """Decorator das rotas exclusivas do onboarding.

    Exige `id_usuario` e `onboarding_pendente` na sessão; sem isso responde 401
    `sessao_invalida`.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("onboarding_pendente"):
            return _resposta_erro("sessao_invalida", "Sessão inválida.", 401)
        return f(*args, **kwargs)
    return wrapper


def requer_login_ou_onboarding_pendente(f):
    """Libera a rota se houver `id_usuario` e a sessão estiver completa OU em onboarding.

    - Com onboarding pendente: só confirma `id_usuario` e segue, sem passar
      pela checagem base (que rejeitaria justamente por haver onboarding
      pendente) nem preencher o `g` (faltam `id_empresa`, `is_admin` etc.). As
      rotas que usam este decorator devem obter o usuário por
      `get_usuario_sessao()` ou `get_id_usuario_sessao()`, nunca por
      `g.id_empresa`, que não existe nesse ramo.
    - Com sessão completa: faz a mesma checagem do decorator de login (checagem
      base e preenchimento do `g`), reaproveitada para não divergir se esses
      helpers mudarem.

    Não inclui a checagem de senha atualizada, pensada para a leitura de dados
    clínicos sensíveis, um caso diferente do cadastro de 2FA. Se um dia o
    cadastro de 2FA precisar dela, aplicar empilhando o decorator na rota
    específica, não aqui.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario"):
            return _resposta_erro("sessao_invalida", "Sessão inválida.", 401)

        if session.get("onboarding_pendente"):
            return f(*args, **kwargs)

        erro = _checagem_base_sessao()
        if erro:
            return erro
        _popula_g()
        return f(*args, **kwargs)
    return wrapper