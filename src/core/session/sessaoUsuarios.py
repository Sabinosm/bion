"""
sessaoUsuarios.py

Base do pacote de sessão: leitura dos dados do usuário e da empresa a partir do
cookie de sessão, mais os helpers que os decorators dos outros módulos
compartilham (respostas de erro padrão e preenchimento do `g`).

Não define decorators e não importa nenhum outro módulo de sessão, justamente
para evitar ciclo, já que todos dependem deste. Os getters leem apenas o
cookie, que guarda identidade, privilégios, função clínica e empresa como
estavam no login (as rotas que pedem revalidam isso contra o banco, ver
sessaoPrivilegios.py); as exceções são o que carrega o usuário completo e o que
descobre o UUID da empresa, que consultam o banco. Por isso só são confiáveis
depois que um decorator de sessão já validou que a sessão está liberada.

Todas as respostas de bloqueio dos decorators do pacote têm o mesmo formato
(`status`, `erro` e `message`), montado por um único helper daqui.
"""

from typing import Optional

from flask import session, jsonify, g


_CHAVE_CACHE_USUARIO = "_usuario_sessao_cache"


def _usuario_sessao():
    """Usuário logado, carregado do banco, ou None se não houver sessão.

    Usar quando se precisa do objeto completo e atualizado (nome, telefone,
    status atual: dados que podem ter mudado desde o login). Para saber só a
    empresa, o caso mais comum, prefira `get_id_empresa_sessao`, que não faz
    query.

    O usuário carregado fica guardado no `g`, então chamadas repetidas na
    mesma requisição (decorators e view) consultam o banco uma vez só.
    """
    uid = session.get("id_usuario")
    if not uid:
        return None

    em_cache = g.get(_CHAVE_CACHE_USUARIO)
    if em_cache is not None and em_cache.id == uid:
        return em_cache

    from src.domains.usuario.repository import UsuarioRepository
    usuario = UsuarioRepository().find_by_id(uid)
    if usuario is not None:
        setattr(g, _CHAVE_CACHE_USUARIO, usuario)
    return usuario


def get_usuario_sessao():
    """Versão pública de `_usuario_sessao`: o Usuario logado (consulta o banco, uma vez por requisição) ou None."""
    return _usuario_sessao()


def get_id_usuario_sessao() -> Optional[int]:
    """Id interno do usuário logado, ou None."""
    return session.get("id_usuario") or None


def get_uuid_usuario_sessao() -> Optional[str]:
    """UUID do usuário logado, ou None."""
    return session.get("uuid_usuario") or None


def get_id_empresa_sessao() -> Optional[int]:
    """Id da empresa direto da sessão, sem tocar o banco.

    Só é confiável DEPOIS de um decorator de sessão ter rodado, pois eles
    garantem que a sessão existe e está liberada. Fora de uma rota protegida
    pode devolver None.
    """
    return session.get("id_empresa")


def get_uuid_empresa_sessao() -> Optional[str]:
    """UUID da empresa do usuário logado, ou None se não houver empresa na sessão.

    O login grava só o id da empresa, então na primeira chamada o UUID é
    buscado no banco e guardado na sessão; as seguintes saem direto do cookie.
    """
    uuid_empresa = session.get("uuid_empresa")
    if uuid_empresa:
        return uuid_empresa

    id_empresa = get_id_empresa_sessao()
    if not id_empresa:
        return None

    from src.models import db
    from src.models.corp import Empresa
    empresa = db.session.get(Empresa, id_empresa)
    if empresa is None:
        return None

    session["uuid_empresa"] = empresa.uuid
    return empresa.uuid


def get_is_super_admin_sessao() -> bool:
    """Se o usuário logado é o super admin da empresa (o admin fundador).

    Mesma cautela de `get_id_empresa_sessao`: só confiável depois de um
    decorator de sessão. O padrão é False, valor das sessões antigas (sem a
    chave gravada) e dos usuários comuns.
    """
    return bool(session.get("is_super_admin", False))


def get_is_admin_sessao() -> bool:
    """Se o usuário logado é administrador, tenha ou não função clínica.

    Fonte de verdade única para "é admin": nunca inferido de `funcao_clinica`.
    """
    return bool(session.get("is_admin", False))


def get_funcao_clinica_sessao() -> Optional[str]:
    """Função clínica do usuário logado ("medico" ou "enfermeiro"), ou None.

    Independente de `is_admin`: um admin pode ter função clínica e vice-versa,
    e as duas são consultadas separadamente.
    """
    return session.get("funcao_clinica")


def _resposta_erro(codigo: str, mensagem: str, http_status: int):
    """Resposta de bloqueio padronizada de todos os decorators do pacote.

    O corpo sempre traz `status` ("error"), `erro` (código estável, para o
    frontend decidir o que fazer) e `message` (texto pronto para exibir).
    """
    return jsonify({"status": "error", "erro": codigo, "message": mensagem}), http_status


def _nao_autenticado():
    """Resposta 401 para requisição sem sessão iniciada."""
    return _resposta_erro("nao_autenticado", "Autenticação necessária.", 401)


def _sem_permissao(papel: str):
    """Resposta 403 para quem está logado mas não tem o papel exigido (`papel` entra na mensagem)."""
    return _resposta_erro("sem_permissao", f"Acesso restrito a {papel}.", 403)


def _popula_g():
    """Copia os dados da sessão já liberada para o `g`, para a rota não reler o cookie.

    Preenche id_usuario, uuid_usuario, id_empresa, is_admin, funcao_clinica e
    is_super_admin. Comum a todo decorator que libera a rota.
    """
    g.id_usuario = get_id_usuario_sessao()
    g.uuid_usuario = get_uuid_usuario_sessao()
    g.id_empresa = get_id_empresa_sessao()
    g.is_admin = get_is_admin_sessao()
    g.funcao_clinica = get_funcao_clinica_sessao()
    g.is_super_admin = get_is_super_admin_sessao()