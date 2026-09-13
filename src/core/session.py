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

DECISÃO CONFIRMADA (revogação de sessão x troca de senha, avaliada e
descartada -- registro pra não reabrir a discussão sem motivo novo):
- Cogitamos contador de versão (`senha_versao`) usado GLOBALMENTE,
  guardar a senha/hash na própria sessão, e uma tabela `SessaoUsuario`
  (sessão revogável com estado no servidor, inclusive política de
  1-sessão-por-usuário). Todas exigem 1 SELECT por requisição
  autenticada (N+1) pra saber se a sessão "envelheceu" -- não existe
  forma de invalidar uma sessão client-side (cookie assinado) sem
  consultar uma fonte de verdade no servidor a cada request; guardar o
  dado revogável DENTRO da própria sessão não resolve nada, porque a
  sessão de quem já está logado (inclusive um invasor) nunca é
  reescrita por uma ação de outra pessoa -- não há canal de
  invalidação remota em sessão client-side.
- Descartado GLOBALMENTE (em `requer_login`) por custo (N+1) sem
  ganho real pra ESCRITA: ações sensíveis de escrita (admin, papel,
  senha, 2FA) já passam por step-up (`step_up.py`), que exige WebAuthn
  ou senha+Google com `prompt=login` -- um invasor só com o cookie de
  sessão não passa nisso de jeito nenhum.
- No lugar, pra rotas comuns: sessão com expiração DESLIZANTE de 10
  min de INATIVIDADE (não de uso contínuo -- cada requisição renova o
  contador). Configurado via `app.config["PERMANENT_SESSION_LIFETIME"]`
  no factory do Flask (`timedelta(minutes=10)`, ver `main.py`) +
  `session.permanent = True` setado no login (senha, Google e
  confirmação de 2FA). Nenhuma mudança de código é necessária NESTE
  arquivo por causa disso -- é config pura do app + 1 linha no(s)
  controller(s) de login.

ADICIONADO (checagem pontual de senha_versao para LEITURA sensível):
- Existe uma categoria intermediária que nem o step-up cobre (não é
  escrita) nem o TTL de 10 min cobre bem o bastante sozinho: LEITURA
  de dados clínicos de paciente. Uma sessão sequestrada pode continuar
  lendo prontuário por até 10 min de inatividade real do dono mesmo
  depois de ele já ter trocado a senha -- pouco tempo, mas dados de
  saúde justificam fechar essa janela também.
- `requer_senha_atualizada(acao_log)` cobre isso: 1 SELECT indexado
  por PK (só a coluna `senha_versao`, via
  `UsuarioRepository.find_senha_versao` -- não carrega o Usuario
  inteiro), aplicado só nas rotas decoradas explicitamente, nunca em
  `requer_login`. Se a versão gravada na sessão no momento do login
  não bate com a atual do banco, a tentativa é logada e a sessão é
  encerrada (403) -- mesmo que ainda estivesse dentro do TTL.
- `senha_versao` é gravada na sessão em TODO login (senha, Google,
  confirmação de 2FA -- ver login.py e oauth.py) e incrementada no
  banco toda vez que `hash_senha` muda (troca pelo próprio usuário ou
  reset por admin -- ver service.py e usuario.py).
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


def _senha_sessao_atualizada(id_usuario: int) -> bool:
    """Compara senha_versao gravada na sessão (no login) contra o valor
    ATUAL no banco. Custa 1 SELECT indexado por PK, de uma única
    coluna -- por isso não entra em `_popula_g`/`requer_login` (rodaria
    em 100% do tráfego autenticado); é chamada só de dentro de
    `requer_senha_atualizada`, nas rotas que o time decidir decorar.

    Retorno: True se a sessão foi criada com a senha_versao vigente
    (ou se a sessão ainda não tem essa chave -- sessão aberta antes
    deste deploy; fail-open aqui é intencional pra não deslogar todo
    mundo no dia do deploy só por essa checagem faltar, diferente do
    fail-closed usado para is_super_admin). False se a senha mudou
    depois deste login.
    """
    versao_sessao = session.get("senha_versao")
    if versao_sessao is None:
        return True

    from src.domains.usuario.repository import UsuarioRepository
    versao_atual = UsuarioRepository().find_senha_versao(id_usuario)
    return versao_atual is not None and versao_sessao == versao_atual


def requer_senha_atualizada(acao_log: str):
    """Decorator para rotas de LEITURA de dados sensíveis (dados
    clínicos de paciente). Além da checagem normal de sessão (login +
    onboarding + mfa), confere se a senha do usuário não mudou desde
    que ESTA sessão foi criada. Se mudou, a sessão é tratada como
    obsoleta para esse tipo de acesso -- registra a tentativa e nega,
    mesmo que a sessão continue dentro do TTL normal e válida para o
    resto do sistema.

    Diferente de `@acao_sensivel` (usado em rotas de ESCRITA, com o
    contrato de (resposta, detalhes) para log de mutação) e diferente
    de `@StepUp.requer_confirmacao_recente` (exige reautenticação ATIVA
    antes de agir): este decorator não pede nada ao usuário, só
    verifica passivamente e loga quando nega -- pensado pra GET.

    Uso:
        @bp.get("/<uuid>/dados-clinicos")
        @requer_senha_atualizada("acesso_dados_clinicos")
        def dados_clinicos(uuid):
            ...

    Parâmetros:
        acao_log: identificador gravado no log quando o acesso é
            negado por sessão com senha desatualizada.

    Retorno:
        Decorator que envolve a view, retornando 403 com
        `sessao_invalida_senha_alterada` quando a checagem falha.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            erro = _checagem_base_sessao()
            if erro:
                return erro

            id_usuario = get_id_usuario_sessao()
            if not _senha_sessao_atualizada(id_usuario):
                # ADICIONADO: log da tentativa negada. Import local
                # para não criar dependência circular entre session.py
                # (usado por praticamente todo domínio) e o módulo de
                # auditoria. Ajustar o caminho/assinatura conforme o
                # módulo real de log de acesso do projeto -- este é um
                # placeholder que segue o mesmo espírito de
                # `acao_sensivel`, mas para leitura negada, não mutação.
                from src.domains.auditoria.service import AuditoriaService
                au = AuditoriaService()
                
                au.registrar_acesso_negado(
                    id_usuario=id_usuario,
                    acao=acao_log,
                    motivo="sessao_com_senha_desatualizada",
                )
                session.clear()
                return jsonify({"erro": "sessao_invalida_senha_alterada"}), 403

            _popula_g()
            return f(*args, **kwargs)
        return wrapper
    return decorator


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