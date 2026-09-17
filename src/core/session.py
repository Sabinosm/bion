"""
Gestão de Cookies e Sessão do Bion (API JSON-only).

Este arquivo é uma FACHADA de compatibilidade: toda a lógica está
modularizada em src/core/sessaoHelpers/, dividida por responsabilidade
(dados de usuário/empresa, autenticação base, papéis/admin, senha
desatualizada, onboarding, mfa). `from src.core.sessao import
requer_login` continua funcionando normalmente.

Se for adicionar algo novo:
- getter de dado de sessão (sem decorator)      -> sessaoHelpers/sessaoUsuarios.py
- checagem básica de sessão / requer_login       -> sessaoHelpers/sessaoAutenticacao.py
- autorização por papel (admin, clínico, super)  -> sessaoHelpers/sessaoPapeis.py
- checagem de senha_versao para leitura sensível -> sessaoHelpers/sessaoSenha.py
- onboarding                                     -> sessaoHelpers/sessaoOnboarding.py
- segundo fator (mfa_pendente)                   -> sessaoHelpers/sessaoMfa.py

E reexportar aqui embaixo, se for algo de uso público no resto do projeto.
"""
# Reexportado por compatibilidade com código que faz
# `from src.core.sessao import session`. Para uso novo, prefira
# importar direto de `flask`.
from flask import session, jsonify, g

# --- sessaoUsuarios: getters de dados do usuário/empresa na sessão ---
from src.core.sessaoHelpers(
    get_id_usuario_sessao,
    get_uuid_usuario_sessao,
    get_usuario_sessao,
    get_id_empresa_sessao,
    get_uuid_empresa_sessao,
    get_is_super_admin_sessao,
    get_is_admin_sessao,
    get_funcao_clinica_sessao,
)

# --- sessaoAutenticacao: checagem base de sessão + requer_login ---
from src.core.sessaoHelpers(
    requer_login,
    ja_logado,
)

# --- sessaoPapeis: autorização por papel (admin / clínico / super admin) ---
from src.core.sessaoHelpers(
    requer_admin,
    requer_papel_clinico,
    requer_admin_ou_papel_clinico,
    requer_super_admin,
)

# --- sessaoSenha: checagem de senha_versao para leitura sensível ---
from src.core.sessaoHelpers(
    requer_senha_atualizada,
)

# --- sessaoOnboarding: rotas de onboarding e caso híbrido ---
from src.core.sessaoHelpers(
    onboarding_pendente_required,
    requer_login_ou_onboarding_pendente,
)

# --- sessaoMfa: segundo fator pendente ---
from src.core.sessaoHelpers(
    TTL_MFA_PENDENTE_SEGUNDOS,
    iniciar_mfa_pendente,
    mfa_pendente_required,
    _mfa_pendente_expirado,  # só usado internamente por status.py
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