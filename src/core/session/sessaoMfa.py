"""
sessaoMfa.py

Estado de segundo fator pendente (`mfa_pendente`) e o decorator das rotas que o
confirmam. Esse estado vale por um prazo FIXO de 5 minutos contados desde a
criação, que não desliza com a atividade: diferente do prazo de inatividade da
sessão completa, nenhuma requisição posterior o renova. É isso que impede um
cookie em `mfa_pendente` de ficar "vivo para sempre" só porque algo continua
tocando a sessão, por exemplo o frontend consultando o status da sessão
repetidamente enquanto o usuário procura o celular para o TOTP.

Depende apenas de sessaoUsuarios.py (resposta de bloqueio padronizada).
"""

import time
from functools import wraps

from flask import session

from src.core.session.sessaoUsuarios import _resposta_erro

TTL_MFA_PENDENTE_SEGUNDOS = 5 * 60  # 5 min, fixo: não desliza com atividade


def iniciar_mfa_pendente():
    """Marca a sessão como aguardando o segundo fator, com o instante de criação.

    Deve ser chamada SEMPRE no lugar de gravar `session["mfa_pendente"] = True`
    direto (login por senha, login por Google e conclusão de onboarding de
    quem já tinha fator), para a gravação do timestamp não ser duplicada. O
    timestamp NÃO é renovado por nenhuma requisição seguinte, o que torna a
    janela fixa.
    """
    session["mfa_pendente"] = True
    session["mfa_pendente_criado_em"] = time.time()


def _mfa_pendente_expirado() -> bool:
    """True se o estado `mfa_pendente` passou do prazo fixo.

    Também True se não houver timestamp gravado (sessão antiga, de antes desse
    controle existir): é tratada como expirada, fail-closed, para não ficar
    pendente para sempre por falta do campo.
    """
    criado_em = session.get("mfa_pendente_criado_em")
    if criado_em is None:
        return True
    return (time.time() - criado_em) > TTL_MFA_PENDENTE_SEGUNDOS


def mfa_pendente_required(f):
    """Decorator das rotas do segundo fator, usadas só por quem está em `mfa_pendente`.

    Exige `id_usuario` e `mfa_pendente` na sessão e, além disso, expira o
    estado pelo prazo fixo desde a criação (ver `iniciar_mfa_pendente`), não
    importa quantas requisições tenham acontecido nesse meio-tempo. Se a
    sessão não estiver nesse estado, ou tiver expirado (caso em que ela é
    limpa), responde 401 `sessao_invalida`.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("mfa_pendente"):
            return _resposta_erro("sessao_invalida", "Sessão inválida.", 401)
        if _mfa_pendente_expirado():
            session.clear()
            return _resposta_erro("sessao_invalida", "Sessão expirada. Faça login novamente.", 401)
        return f(*args, **kwargs)
    return wrapper