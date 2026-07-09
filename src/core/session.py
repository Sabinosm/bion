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


def get_usuario_sessao():
    return _usuario_sessao()


def id_empresa_sessao():
    """
    Retorna id_empresa direto da sessão, sem tocar o banco.

    Só é confiável DEPOIS de @requer_login (ou de um dos decorators de
    papel abaixo) já ter rodado — eles garantem que a sessão existe e
    está liberada. Chamar isso fora de uma rota protegida pode
    retornar None.
    """
    return session.get("id_empresa")


def _nao_autenticado():
    return jsonify({"status": "error", "message": "Autenticação necessária."}), 401


def _sem_permissao(papel):
    return jsonify({"status": "error", "message": f"Acesso restrito a {papel}."}), 403


def _requer_papeis(*papeis_permitidos):
    """Fábrica interna de decorator — usada pelos requer_* nomeados abaixo."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("id_usuario"):
                return _nao_autenticado()

            if session.get("onboarding_pendente"):
                return jsonify({"erro": "onboarding_requerido"}), 403

            if session.get("mfa_pendente"):
                return jsonify({"erro": "mfa_requerido"}), 401

            if papeis_permitidos and session.get("tipo_usuario") not in papeis_permitidos:
                rotulo = " ou ".join(papeis_permitidos)
                return _sem_permissao(rotulo)

            g.id_usuario = session["id_usuario"]
            g.uuid_usuario = session.get("uuid_usuario")
            g.id_empresa = session.get("id_empresa")
            g.tipo_usuario = session.get("tipo_usuario")

            return f(*args, **kwargs)
        return wrapper
    return decorator


def requer_login(f):
    """
    Bloqueia qualquer rota clínica/normal a menos que a sessão esteja
    TOTALMENTE liberada: sem onboarding pendente e sem 2FA pendente.

    Também popula g.id_usuario / g.id_empresa / g.tipo_usuario, pra
    rota não precisar reler a sessão manualmente.
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
# Decorators de papel (tipo_usuario)
#
# Mantidos como funções nomeadas individuais (requer_medico, requer_admin,
# etc) para não quebrar imports já existentes em outras rotas. Por baixo,
# todos usam _requer_papeis() para não repetir a mesma checagem 4 vezes.
#
# Cada um destes já inclui a checagem COMPLETA de sessão (autenticado +
# onboarding concluído + mfa concluído — igual requer_login), então não
# é necessário empilhar @requer_login junto: @requer_medico sozinho já
# garante tudo. Empilhar os dois juntos não quebra nada, só é redundante.
# ---------------------------------------------------------------------------


# def _ja_logado():
#     def decorator(f):
#         @wraps(f)
#         def wrapper(*args, **kwargs):
#            if session.get("id_usuario"):
#                 return jsonify({"status": "error", "message": "Usuario já logado."}), 409
#            else :
#                return f(*args, **kwargs)
#         return wrapper
#     return decorator
        

def requer_papel(*papeis_permitidos):
    """
    Versão genérica/parametrizável, pra combinações novas que ainda não
    têm um nome dedicado acima (ex: uma rota futura que precise liberar
    para "admin" e "medico" ao mesmo tempo, sem criar mais um
    requer_admin_ou_medico só pra esse caso).

    Uso:
        @requer_papel("admin", "medico")
        def rota(): ...
    """
    return _requer_papeis(*papeis_permitidos)