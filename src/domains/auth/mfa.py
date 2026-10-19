"""
mfa.py

Decisão de qual método de segundo fator (2FA) usar para um usuário. O 2FA é
sempre obrigatório no login, por senha ou por Google, então este módulo não
decide "se" exigir, apenas "qual" método oferecer ou tentar primeiro.

Os métodos cadastráveis são WebAuthn e TOTP, nessa ordem de preferência. Na
reconfirmação de identidade antes de ações sensíveis (step-up) existe ainda
um terceiro caminho, senha mais Google, que cobre quem não tem nenhum dos
dois fatores.
"""

from typing import Optional

from src.models.usuarios.credencial_totp import CredencialTOTP
from src.models.usuarios.credencial_webauthn import CredencialWebAuthn


def _tem_webauthn(id_usuario) -> bool:
    """True se o usuário tem ao menos uma credencial WebAuthn."""
    return CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).first() is not None


def _tem_totp_confirmado(id_usuario) -> bool:
    """True se o usuário tem um TOTP já confirmado."""
    return CredencialTOTP.query.filter_by(
        id_usuario=id_usuario, confirmado=True
    ).first() is not None


def metodo_2fa_preferencial(id_usuario) -> Optional[str]:
    """Método de 2FA que deve ser OFERECIDO PRIMEIRO no login do usuário.

    Retorna "webauthn" se houver 1+ credencial WebAuthn; senão "totp" se
    houver TOTP confirmado; senão None.

    None só deveria ocorrer em contas legadas sem nenhum fator migrado. Quem
    chama deve tratá-lo como estado inconsistente a resolver manualmente
    (ex.: por um admin), nunca como "sem 2FA, libera direto", opção que não
    existe no sistema.
    """
    if _tem_webauthn(id_usuario):
        return "webauthn"
    if _tem_totp_confirmado(id_usuario):
        return "totp"
    return None


def usuario_tem_algum_2fa(id_usuario) -> bool:
    """True se o usuário tem WebAuthn OU TOTP confirmado."""
    return metodo_2fa_preferencial(id_usuario) is not None


def metodo_stepup(id_usuario) -> str:
    """Método que o step-up deve tentar primeiro: "webauthn", "totp" ou "senha_google".

    Segue a mesma ordem de preferência de `metodo_2fa_preferencial`, mas
    resolve a conta sem nenhum fator para "senha_google", porque, ao contrário
    do login, o step-up mantém o fallback senha mais Google para quem não tem
    nenhum fator.
    """
    return metodo_2fa_preferencial(id_usuario) or "senha_google"


def metodos_2fa_disponiveis(id_usuario) -> list[str]:
    """TODOS os métodos de 2FA utilizáveis pelo usuário, com WebAuthn primeiro.

    Existe para o frontend poder oferecer escolha quando há mais de um
    método (ver /auth/status). Lista vazia só deveria ocorrer no mesmo caso
    legado descrito em `metodo_2fa_preferencial`.
    """
    metodos = []
    if _tem_webauthn(id_usuario):
        metodos.append("webauthn")
    if _tem_totp_confirmado(id_usuario):
        metodos.append("totp")
    return metodos