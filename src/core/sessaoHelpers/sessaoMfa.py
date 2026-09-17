"""
sessaoMfa.py -- Estado de segundo fator pendente (mfa_pendente), com
TTL fixo desde a criação (não desliza com atividade).

Sem dependência de outros sessao*.py.
"""

import time
from functools import wraps
from flask import session, jsonify

TTL_MFA_PENDENTE_SEGUNDOS = 5 * 60  # 5 min, fixo -- não desliza com atividade


def iniciar_mfa_pendente():
    """Marca a sessão como aguardando segundo fator, com timestamp de
    criação fixo. Chamar SEMPRE no lugar de `session["mfa_pendente"] = True`
    direto -- login.py e oauth.py usam este helper para não duplicar
    a gravação do timestamp em dois arquivos.

    O timestamp NÃO é renovado por nenhuma requisição subsequente
    (diferente do TTL de inatividade da sessão completa, que desliza a
    cada request) -- é o que torna esta janela fixa mesmo que o
    frontend fique consultando /auth/status repetidamente enquanto o
    usuário procura o celular para o TOTP.
    """
    session["mfa_pendente"] = True
    session["mfa_pendente_criado_em"] = time.time()


def _mfa_pendente_expirado() -> bool:
    """True se o estado mfa_pendente já passou do TTL fixo, ou se não
    há timestamp gravado (sessão antiga, de antes deste deploy --
    tratada como expirada, fail-closed, para não ficar pendente para
    sempre por falta do campo).
    """
    criado_em = session.get("mfa_pendente_criado_em")
    if criado_em is None:
        return True
    return (time.time() - criado_em) > TTL_MFA_PENDENTE_SEGUNDOS


def mfa_pendente_required(f):
    """Usado só nas rotas do segundo fator (login recorrente).

    Além de exigir id_usuario + mfa_pendente na sessão, também expira
    o estado por TEMPO FIXO desde a criação (TTL_MFA_PENDENTE_SEGUNDOS),
    independente de quantas requisições aconteceram nesse meio-tempo --
    ver iniciar_mfa_pendente() e _mfa_pendente_expirado() acima. Isso
    fecha a janela em que um cookie de sessão em mfa_pendente ficava
    efetivamente "vivo para sempre" contanto que algo continuasse
    tocando a sessão (ex: /auth/status sendo consultado ao reabrir a
    página), sem o usuário nunca ter provado a senha de novo.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario") or not session.get("mfa_pendente"):
            return jsonify({"erro": "sessao_invalida"}), 401
        if _mfa_pendente_expirado():
            session.clear()
            return jsonify({"erro": "sessao_invalida"}), 401
        return f(*args, **kwargs)
    return wrapper