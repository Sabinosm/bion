"""
Gestão de Cookies e Sessão do Bion (API JSON-only).

CORREÇÃO MANTIDA: no bion.zip original, o controller de login gravava
`session["usuario_uuid"]`, mas estas funções liam `session.get("id_usuario")`.
A sessão nunca era reconhecida como autenticada e `requer_login` sempre
falhava mesmo após login bem-sucedido. Padronizado em `id_usuario`
(chave primária interna, busca mais barata que por uuid); o controller de
auth grava `session["id_usuario"] = usuario.id` no login.

Diferença em relação à versão web: os decorators agora retornam respostas
JSON (401/403) em vez de redirect + flash, já que não há mais páginas HTML
para redirecionar o usuário.

ALTERADO (múltiplos admins por empresa):
- `g.is_super_admin` passa a ser populado em toda rota autenticada, a
  partir de `session["is_super_admin"]` -- gravado no login (por senha
  ou Google) e reforçado na confirmação do 2FA. Ver login.py, oauth.py
  e webauthn_2fa.py.
- Sessões abertas ANTES deste deploy não têm essa chave -- o default
  `False` é intencional (fail-closed): o super admin perde o poder de
  criar/alterar outros admins até relogar, mas nenhum admin comum passa
  a ter esse poder por engano. Avisar isso no deploy.
- `requer_super_admin` foi adicionado como decorator dedicado, para
  rotas onde a exigência é binária (ex: criar admin). Para rotas onde a
  checagem depende do alvo da operação (atualizar/desativar/ativar um
  usuário que pode ou não ser admin), continue usando `requer_admin`
  e faça a checagem fina no service, usando `g.is_super_admin`.

ALTERADO (separação admin/papel clínico, assertivo, sem alias):
- `session["tipo_usuario"]` SAIU por completo. `tipo_usuario` tratava
  "é admin" e "qual profissão clínica" como uma única categoria
  mutuamente exclusiva, o que impedia um admin de também ter uma
  função clínica (ex: dono de clínica pequena que também atende).
- Duas chaves independentes entram no lugar: `session["is_admin"]`
  (bool) e `session["funcao_clinica"]` ("medico"/"enfermeiro"/None).
  As duas podem ser "verdadeiras" ao mesmo tempo no mesmo usuário.
- `requer_papel(...)` foi removido (levanta NotImplementedError se
  chamado) -- não existe tradução automática segura do antigo
  comportamento. Todo uso precisa ser revisto e trocado por
  `requer_admin`, `requer_papel_clinico(...)` ou
  `requer_admin_ou_papel_clinico(...)`, conforme a intenção original
  de cada rota.
"""

from functools import wraps
from flask import session, jsonify, g


def _usuario_sessao():
    """
    Retorna o Usuario logado ou None.

    Útil quando você realmente precisa do objeto Usuario completo e
    atualizado (ex: mostrar nome, telefone, status atual — dados que
    podem ter mudado desde o login e você quer o valor mais recente
    do banco).

    Para saber SÓ a empresa do usuário (o caso mais comum, usado em
    quase toda rota pra filtrar dados), prefira id_empresa_sessao()
    abaixo — evita uma query desnecessária a cada requisição.
    """
    uid = session.get("id_usuario")
    if not uid:
        return None
    from src.domains.usuario.repository import UsuarioRepository
    return UsuarioRepository().find_by_id(uid)

def get_id_usuario_sessao():
    """
    Retorna o id do Usuario logado ou None.
    
    Útil quando você precisa do id do Usuario
    """
    id = session.get("id_usuario")
    if not id:
        return None
    return id

def get_uuid_usuario_sessao():
    """
    Retorna o uuid do Usuario logado ou None.
    
    Útil quando você precisa do uuid do Usuario
    """
    uuid = session.get("uuid_usuario")
    if not uuid:
        return None
    return uuid

def get_usuario_sessao():
    return _usuario_sessao()


def get_id_empresa_sessao():
    """
    Retorna id_empresa direto da sessão, sem tocar o banco.

    Só é confiável DEPOIS de @requer_login (ou de um dos decorators de
    papel abaixo) já ter rodado — eles garantem que a sessão existe e
    está liberada. Chamar isso fora de uma rota protegida pode
    retornar None.
    """
    return session.get("id_empresa")

def get_uuid_empresa_sessao():
    return session.get("uuid_empresa")


def get_is_super_admin_sessao() -> bool:
    """
    Retorna se o usuário logado é o super admin da empresa.

    Mesma cautela de get_id_empresa_sessao(): só confiável depois de
    um decorator de sessão já ter rodado. Default False -- sessões
    antigas (sem a chave gravada) ou usuários comuns caem aqui.
    """
    return bool(session.get("is_super_admin", False))


def get_is_admin_sessao() -> bool:
    """
    Retorna se o usuário logado é administrador (is_admin), independente
    de ter ou não uma função clínica associada.

    ALTERADO: substitui a antiga leitura de session.get("tipo_usuario")
    == "admin". Fonte de verdade única para "é admin" -- nunca
    inferido a partir de funcao_clinica.
    """
    return bool(session.get("is_admin", False))


def get_funcao_clinica_sessao():
    """
    Retorna a função clínica do usuário logado ("medico"/"enfermeiro")
    ou None. Independente de is_admin -- um admin pode ter função
    clínica e vice-versa, as duas são consultadas separadamente.
    """
    return session.get("funcao_clinica")


def _nao_autenticado():
    return jsonify({"status": "error", "message": "Autenticação necessária."}), 401


def _sem_permissao(papel):
    return jsonify({"status": "error", "message": f"Acesso restrito a {papel}."}), 403


def _checagem_base_sessao():
    """
    Checagens comuns a todo decorator de sessão (autenticação, onboarding,
    mfa). Retorna a resposta de erro se algo falhar, ou None se pode
    prosseguir. Fatorado para não repetir em cada fábrica abaixo.
    """
    if not session.get("id_usuario"):
        return _nao_autenticado()
    if session.get("onboarding_pendente"):
        return jsonify({"erro": "onboarding_pendente"}), 403
    if session.get("mfa_pendente"):
        return jsonify({"erro": "mfa_pendente"}), 401
    return None


def _popula_g():
    """Popula g.* com os dados de sessão já liberada. Comum a todo decorator."""
    g.id_usuario = get_id_usuario_sessao()
    g.uuid_usuario = session.get("uuid_usuario")
    g.id_empresa = session.get("id_empresa")
    g.is_admin = get_is_admin_sessao()
    g.funcao_clinica = get_funcao_clinica_sessao()
    g.is_super_admin = get_is_super_admin_sessao()


def _requer_papeis():
    """
    ALTERADO (assertivo, sem alias): a antiga fábrica genérica que
    recebia *papeis_permitidos e comparava contra um único
    session["tipo_usuario"] SAIU. Ela não pode mais expressar
    corretamente "admin" e "médico" como dimensões independentes que
    coexistem no mesmo usuário.

    Mantida sem parâmetros — cobre só a checagem de sessão básica
    (autenticado + onboarding + mfa), usada por requer_login. Para
    exigências de papel, ver requer_admin, requer_papel_clinico e
    requer_admin_ou_papel_clinico abaixo.
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


def requer_admin(f):
    """
    Bloqueia a rota a menos que o usuário logado tenha is_admin=True.

    Substitui os usos de @requer_papel("admin"). Não depende de
    funcao_clinica -- um admin com ou sem papel clínico associado
    passa igualmente por este decorator.
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

    Substitui os usos de @requer_papel("medico") / @requer_papel("enfermeiro").
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
    a rota antiga fazia algo como @requer_papel("admin", "medico")
    (liberar para qualquer um dos dois).

    Uso:
        @requer_admin_ou_papel_clinico("medico")
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            erro = _checagem_base_sessao()
            if erro:
                return erro
            eh_admin = get_is_admin_sessao()
            papel_ok = get_funcao_clinica_sessao() in papeis_clinicos_permitidos
            if not (eh_admin or papel_ok):
                rotulo = " ou ".join(("administrador",) + papeis_clinicos_permitidos)
                return _sem_permissao(rotulo)
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
    sessão manualmente. (g.tipo_usuario foi REMOVIDO -- ver g.is_admin
    e g.funcao_clinica.)
    """
    return _requer_papeis()(f)


def onboarding_pendente_required(f):
    """Usado só nas rotas de onboarding (definir senha, cadastrar WebAuthn)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("onboarding_pendente"):
            return jsonify({"erro": "sessao_invalida"}), 401
        return f(*args, **kwargs)
    return wrapper


def mfa_pendente_required(f):
    """Usado só nas rotas do segundo fator (login recorrente)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("mfa_pendente"):
            return jsonify({"erro": "sessao_invalida"}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Decorators de papel (is_admin / funcao_clinica)
#
# requer_admin, requer_papel_clinico e requer_admin_ou_papel_clinico
# (definidos acima) cobrem as combinações de autorização por papel.
#
# Cada um já inclui a checagem COMPLETA de sessão (autenticado +
# onboarding concluído + mfa concluído — igual requer_login), então não
# é necessário empilhar @requer_login junto: @requer_admin sozinho já
# garante tudo. Empilhar os dois juntos não quebra nada, só é redundante.
#
# Atenção: empilhar @requer_admin com @requer_papel_clinico(...) exige
# as DUAS condições (AND) -- 
# use requer_admin_ou_papel_clinico(...) quando a intenção é liberar para qualquer um dos dois (OR).
# ---------------------------------------------------------------------------


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

def requer_papel(*papeis_permitidos):
    """
    REMOVIDO (assertivo, sem alias de compatibilidade).

    Este decorator comparava contra um único session["tipo_usuario"],
    que não existe mais -- "admin" e papel clínico agora são dimensões
    independentes (is_admin + funcao_clinica) e podem coexistir no
    mesmo usuário. Não há tradução automática correta de
    @requer_papel(...) para o novo modelo: a chamada precisa ser
    revista caso a caso e trocada por uma das opções abaixo:

      @requer_admin                              -- era @requer_papel("admin")
      @requer_papel_clinico("medico")             -- era @requer_papel("medico")
      @requer_papel_clinico("medico", "enfermeiro")
      @requer_admin_ou_papel_clinico("medico")     -- era @requer_papel("admin", "medico")

    Levanta erro imediato para forçar a correção no ponto de uso, em
    vez de autorizar (ou negar) incorretamente de forma silenciosa.
    """
    raise NotImplementedError(
        "requer_papel(...) foi removido. Troque por @requer_admin, "
        "@requer_papel_clinico(...) ou @requer_admin_ou_papel_clinico(...) "
        "conforme a intenção original da rota."
    )


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
        if not session.get("id_usuario"):
            return _nao_autenticado()

        if session.get("onboarding_pendente"):
            return jsonify({"erro": "onboarding_pendente"}), 403

        if session.get("mfa_pendente"):
            return jsonify({"erro": "mfa_pendente"}), 401

        # ALTERADO: era session.get("tipo_usuario") != "admin" -- lia o
        # campo errado. Super admin é sempre is_admin=True também (ver
        # Empresa.cadastrar_com_admin), mas a fonte de verdade correta
        # para "é admin" é is_admin, não mais tipo_usuario.
        if not session.get("is_admin") or not session.get("is_super_admin"):
            return _sem_permissao("administrador principal")

        _popula_g()
        g.is_super_admin = True

        return f(*args, **kwargs)
    return wrapper