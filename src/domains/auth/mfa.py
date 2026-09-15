"""Decisão de qual método de 2FA usar -- 2FA agora é SEMPRE obrigatório
(login por senha e por Google), então este módulo não decide mais
"se" exigir, só "qual" método tentar primeiro.

ALTERADO (2FA sempre obrigatório): versão anterior deste módulo
(`usuario_tem_redundancia_2fa`) decidia se o 2FA era obrigatório com
base em ter 2+ fatores. Essa lógica foi abandonada -- agora todo
usuário tem WebAuthn e/ou TOTP obrigatoriamente desde o onboarding
(ver onboarding.py), então a pergunta relevante deixou de ser "tem
fatores suficientes?" e passou a ser "qual fator tentar primeiro?".
"""

from src.models.usuarios.credencial_totp import CredencialTOTP
from src.models.usuarios.credencial_webauthn import CredencialWebAuthn


def metodo_2fa_preferencial(id_usuario) -> str | None:
    """Retorna qual método deve ser OFERECIDO PRIMEIRO no login desse
    usuário: "webauthn" se tiver 1+ credencial WebAuthn, senão "totp"
    se tiver TOTP confirmado, senão None.

    None só deveria ocorrer para usuários criados antes desta mudança
    (dados legados sem nenhum fator ainda migrado) -- todo usuário que
    passou pelo onboarding atual tem pelo menos um dos dois. Quem
    chama deve tratar None como um estado inconsistente a ser
    resolvido manualmente (ex: admin), não como "sem 2FA, libera
    direto" -- essa opção não existe mais no sistema.
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
    decidir o método do STEP-UP (que ainda mantém fallback senha+Google
    para quem não tem nenhum dos dois, ver step_up.py).
    """
    return metodo_2fa_preferencial(id_usuario) is not None

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