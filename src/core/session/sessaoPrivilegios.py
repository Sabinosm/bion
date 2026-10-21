"""
sessaoPrivilegios.py

Revalidação sob demanda dos privilégios gravados na sessão. O cookie guarda
os privilégios do usuário (administrador, função clínica, super admin) e a
empresa como estavam no login; sem revalidar, retirar o papel de alguém ou
desativá-lo só faria efeito quando a sessão dele terminasse.

A revalidação NÃO roda em toda requisição. Ela só acontece nas rotas cujo
decorator de papel pede (parâmetro `revalidar`): por padrão ligada nas rotas
de administrador, onde o custo de uma consulta ao banco compensa, e desligada
nas de função clínica, de tráfego muito maior. Quando roda, é uma consulta por
PK, que o `g` reaproveita se a view também carregar o usuário.

Depende apenas de sessaoUsuarios.py.
"""

from flask import session

from src.core.session.sessaoUsuarios import _usuario_sessao, _resposta_erro


def revalidar_privilegios():
    """Relê o usuário do banco e confere se a sessão ainda é válida para esta requisição.

    Devolve a resposta de bloqueio, ou None se a rota pode prosseguir:
      - usuário inexistente, inativo ou de uma empresa diferente da gravada na
        sessão: a sessão é encerrada e responde 401 `sessao_invalida`;
      - caso contrário, `is_admin`, `funcao_clinica` e `is_super_admin` da
        sessão são sincronizados com o banco (para mais ou para menos), de
        modo que a checagem de papel que vem a seguir já usa dados atuais.
    """
    usuario = _usuario_sessao()
    if (
        usuario is None
        or usuario.status == "inativo"
        or usuario.id_empresa != session.get("id_empresa")
    ):
        session.clear()
        return _resposta_erro("sessao_invalida", "Sessão inválida. Faça login novamente.", 401)

    session["is_admin"] = bool(usuario.is_admin)
    session["funcao_clinica"] = usuario.funcao_clinica
    session["is_super_admin"] = bool(usuario.is_super_admin)
    return None