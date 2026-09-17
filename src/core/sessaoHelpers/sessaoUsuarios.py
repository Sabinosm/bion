"""
sessaoUsuarios.py -- Leitura de dados do usuário/empresa a partir da sessão.

Sem decorators aqui. Este módulo é a base: getters puros que leem
`session` (e, no caso de `_usuario_sessao`, o banco) e os helpers
`_nao_autenticado` / `_sem_permissao` / `_popula_g` usados pelos
decorators em sessaoAutenticacao.py, sessaoPapeis.py e sessaoSenha.py.

Não importa nada de outro sessao*.py -- evita ciclo, já que é
justamente o módulo do qual os outros dependem.
"""

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


def _popula_g():
    """Popula g.* com os dados de sessão já liberada. Comum a todo decorator."""
    g.id_usuario = get_id_usuario_sessao()
    g.uuid_usuario = session.get("uuid_usuario")
    g.id_empresa = session.get("id_empresa")
    g.is_admin = get_is_admin_sessao()
    g.funcao_clinica = get_funcao_clinica_sessao()
    g.is_super_admin = get_is_super_admin_sessao()