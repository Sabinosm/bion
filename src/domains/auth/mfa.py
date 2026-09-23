"""Decisão de qual método de 2FA usar. 2FA é sempre obrigatório (login
por senha e por Google) — este módulo não decide "se" exigir, só "qual"
método tentar primeiro.
"""

from src.models.usuarios.credencial_totp import CredencialTOTP
from src.models.usuarios.credencial_webauthn import CredencialWebAuthn


def metodo_2fa_preferencial(id_usuario) -> str | None:
    """Retorna qual método deve ser OFERECIDO PRIMEIRO no login desse
    usuário: "webauthn" se tiver 1+ credencial WebAuthn, senão "totp"
    se tiver TOTP confirmado, senão None.

    None só deveria ocorrer para usuários com dados legados sem nenhum
    fator ainda migrado. Quem chama deve tratar None como um estado
    inconsistente a ser resolvido manualmente (ex: admin), não como
    "sem 2FA, libera direto" -- essa opção não existe no sistema.
    """
    tem_webauthn = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).first() is not None
    if tem_webauthn:
        return "webauthn"

    tem_totp = CredencialTOTP.query.filter_by(
        id_usuario=id_usuario, confirmado=True
    ).first() is not None
    if tem_totp:
        return "totp"

    return None


def usuario_tem_algum_2fa(id_usuario) -> bool:
    """True se o usuário tem WebAuthn OU TOTP cadastrado -- usado para
    decidir o método do STEP-UP (que mantém fallback senha+Google para
    quem não tem nenhum dos dois, ver step_up.py).
    """
    return metodo_2fa_preferencial(id_usuario) is not None


def metodo_stepup(id_usuario) -> str:
    """Retorna qual método o STEP-UP deve tentar primeiro: "webauthn"
    ou "totp" se o usuário tiver algum dos dois (mesma ordem de
    preferência de `metodo_2fa_preferencial`), ou "senha_google" caso
    não tenha nenhum dos dois cadastrado.

    Diferente de `metodo_2fa_preferencial` (que devolve None para
    contas legadas sem fator migrado e deixa quem chama decidir o que
    fazer com isso), esta função já resolve esse caso para "senha_google"
    -- porque, ao contrário do login, o step-up sempre tem uma saída
    (ver step_up.py para o racional completo do fallback).
    """
    metodo = metodo_2fa_preferencial(id_usuario)
    return metodo or "senha_google"


def metodos_2fa_disponiveis(id_usuario) -> list[str]:
    """Retorna TODOS os métodos de 2FA cadastrados e utilizáveis pelo
    usuário, em ordem de preferência de exibição (WebAuthn primeiro).

    Diferente de `metodo_2fa_preferencial()` -- que devolve só o
    primeiro que encontra, usado para decidir automaticamente qual
    tentar no STEP-UP -- esta função existe para o frontend poder
    OFERECER ESCOLHA ao usuário quando mais de um método está
    disponível (ver /auth/status, tela de escolha no login). Lista
    vazia só deveria ocorrer para o mesmo caso de dado legado descrito
    em `metodo_2fa_preferencial`.
    """
    metodos = []

    tem_webauthn = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).first() is not None
    if tem_webauthn:
        metodos.append("webauthn")

    tem_totp = CredencialTOTP.query.filter_by(
        id_usuario=id_usuario, confirmado=True
    ).first() is not None
    if tem_totp:
        metodos.append("totp")

    return metodos