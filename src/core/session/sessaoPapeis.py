"""
sessaoPapeis.py

Decorators de autorização por papel: administrador, função clínica (médico ou
enfermeiro), qualquer um dos dois e super admin. Cada um já inclui a checagem
COMPLETA de sessão (autenticado, onboarding concluído, 2FA concluído), a mesma
do decorator de login, então um decorator sozinho já garante tudo. Empilhar o
de login junto não quebra nada, só é redundante.

Atenção: empilhar o decorator de administrador com o de função clínica exige as
DUAS condições (AND). Para liberar a rota a qualquer um dos dois (OR), usar o
decorator combinado.

Todos são montados sobre a mesma fábrica de sessaoAutenticacao.py, que
executa a checagem de sessão, a revalidação opcional, a permissão e por fim
preenche o `g`.

Revalidação (parâmetro `revalidar`): relê o usuário do banco antes da checagem
de papel, para que um papel retirado, um usuário desativado ou uma troca de
empresa valham na hora, e não só quando a sessão terminar. Custa uma consulta
por requisição na rota, por isso o padrão depende do decorator: ligada nos de
administrador (tráfego baixo, privilégio alto) e desligada no de função
clínica (tráfego alto). Pode ser trocada em qualquer um.
"""

from src.core.session.sessaoUsuarios import (
    get_is_admin_sessao,
    get_is_super_admin_sessao,
    get_funcao_clinica_sessao,
    _sem_permissao,
)
from src.core.session.sessaoAutenticacao import _requer_papeis


def _exigir_admin():
    if not get_is_admin_sessao():
        return _sem_permissao("administrador")
    return None


def _exigir_super_admin():
    if not (get_is_admin_sessao() and get_is_super_admin_sessao()):
        return _sem_permissao("administrador principal")
    return None


def requer_admin(f=None, *, revalidar: bool = True):
    """Bloqueia a rota a menos que o usuário logado tenha is_admin=True.

    Não depende de função clínica: um admin com ou sem papel clínico passa
    igualmente. Por padrão revalida contra o banco (papel, status e empresa).

    Uso:
        @requer_admin
        @requer_admin(revalidar=False)
    """
    decorator = _requer_papeis(_exigir_admin, revalidar=revalidar)
    return decorator(f) if f is not None else decorator


def requer_papel_clinico(*papeis_permitidos: str, revalidar: bool = False):
    """Bloqueia a rota a menos que a função clínica do usuário esteja entre `papeis_permitidos`.

    Não depende de is_admin: um médico que também é admin passa igualmente,
    contanto que tenha o papel clínico. Por padrão NÃO revalida contra o
    banco (tráfego alto); usar `revalidar=True` nas rotas em que mudar o papel
    precisa valer na hora.

    Uso:
        @requer_papel_clinico("medico")
        @requer_papel_clinico("medico", "enfermeiro")
        @requer_papel_clinico("medico", revalidar=True)
    """
    def verificar():
        if get_funcao_clinica_sessao() not in papeis_permitidos:
            return _sem_permissao(" ou ".join(papeis_permitidos))
        return None

    return _requer_papeis(verificar, revalidar=revalidar)


def requer_admin_ou_papel_clinico(*papeis_clinicos_permitidos: str, revalidar: bool = True):
    """Libera a rota se o usuário for admin OU tiver uma das funções clínicas informadas (OR, não AND).

    Existe porque empilhar o decorator de administrador com o de função
    clínica exigiria as duas condições ao mesmo tempo, o que é mais restritivo
    que o pretendido. Usar quando a rota deve liberar para qualquer um dos
    dois (ex.: admin ou médico). Por padrão revalida contra o banco, pois
    envolve o privilégio de administrador.

    Uso:
        @requer_admin_ou_papel_clinico("medico")
        @requer_admin_ou_papel_clinico("medico", revalidar=False)
    """
    def verificar():
        papel_ok = get_funcao_clinica_sessao() in papeis_clinicos_permitidos
        if not (get_is_admin_sessao() or papel_ok):
            return _sem_permissao(" ou ".join(("administrador",) + papeis_clinicos_permitidos))
        return None

    return _requer_papeis(verificar, revalidar=revalidar)


def requer_super_admin(f=None, *, revalidar: bool = True):
    """Bloqueia a rota a menos que o usuário seja o super admin da empresa (o admin fundador).

    Use quando a exigência é binária para a rota inteira (ex.: criar um novo
    admin). Quando a checagem depende do ALVO da operação (ex.: atualizar ou
    desativar um usuário que pode ou não ser admin), use o decorator de
    administrador na rota e faça a checagem fina no service com
    `g.is_super_admin`, já que um decorator não conhece o alvo antes de a rota
    rodar. Por padrão revalida contra o banco.

    Uso:
        @requer_super_admin
        @requer_super_admin(revalidar=False)
    """
    decorator = _requer_papeis(_exigir_super_admin, revalidar=revalidar)
    return decorator(f) if f is not None else decorator