
from flask import session, g

from .sessaoUsuarios import (
    get_id_usuario_sessao,
    get_uuid_usuario_sessao,
    get_usuario_sessao,
    get_id_empresa_sessao,
    get_uuid_empresa_sessao,
    get_is_super_admin_sessao,
    get_is_admin_sessao,
    get_funcao_clinica_sessao,
)
from .sessaoAutenticacao import (
    requer_login,
    ja_logado,
)
from .sessaoPapeis import (
    requer_admin,
    requer_papel_clinico,
    requer_admin_ou_papel_clinico,
    requer_super_admin,
)
from .sessaoSenha import (
    requer_senha_atualizada,
)
from .sessaoOnboarding import (
    onboarding_pendente_required,
    requer_login_ou_onboarding_pendente,
)
from .sessaoMfa import (
    TTL_MFA_PENDENTE_SEGUNDOS,
    iniciar_mfa_pendente,
    mfa_pendente_required,
    _mfa_pendente_expirado,
)

__all__ = [
    # sessaoUsuarios
    "get_id_usuario_sessao",
    "get_uuid_usuario_sessao",
    "get_usuario_sessao",
    "get_id_empresa_sessao",
    "get_uuid_empresa_sessao",
    "get_is_super_admin_sessao",
    "get_is_admin_sessao",
    "get_funcao_clinica_sessao",
    # sessaoAutenticacao
    "requer_login",
    "ja_logado",
    # sessaoPapeis
    "requer_admin",
    "requer_papel_clinico",
    "requer_admin_ou_papel_clinico",
    "requer_super_admin",
    # sessaoSenha
    "requer_senha_atualizada",
    # sessaoOnboarding
    "onboarding_pendente_required",
    "requer_login_ou_onboarding_pendente",
    # sessaoMfa
    "TTL_MFA_PENDENTE_SEGUNDOS",
    "iniciar_mfa_pendente",
    "mfa_pendente_required",
    "_mfa_pendente_expirado",
]