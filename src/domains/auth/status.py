"""Rota informativa de status de sessão.

Diferente de `/auth/me`, esta rota não bloqueia -- apenas informa em
que estado a sessão está. Usada pela página pós-login logo após o
redirect do Google, para decidir se o usuário deve ir para onboarding,
confirmação de 2FA, ou dashboard. Mantém o contrato de resposta somente
em JSON, mesmo sendo uma rota de apoio à navegação.
"""

from flask import Blueprint, session, jsonify, g
from src.core.responses import json_error, json_success
from src.core.session import requer_login, get_usuario_sessao

bp_status = Blueprint("status", __name__)


@bp_status.route("/status", methods=["GET"])
def status_sessao():
    from src.models.usuarios import Usuario
    """Retorna o estado atual da sessão sem exigir autenticação completa.

    `onboarding_pendente` só cobre a definição de senha (WebAuthn não
    faz mais parte do onboarding, fica em configurações). `mfa_pendente`
    só ocorre após login por senha para usuário com WebAuthn já
    cadastrado -- login via Google nunca entra nesse estado, libera
    sessão completa direto (ou onboarding_pendente, se faltar senha).

    Retorno:
        200 com `status: autenticado`, `onboarding_pendente` (incluindo
        `senha_definida: bool` para o frontend saber se pode pular a
        etapa de senha) ou `mfa_pendente` (incluindo `metodo` e
        `tentativas_restantes`, para o frontend decidir entre tentar de
        novo ou oferecer reautenticação por senha ou Google).
        401 com `status: nao_autenticado` se não houver sessão iniciada.
    """
    if not get_usuario_sessao():
        return jsonify({"status": "nao_autenticado"}), 401

    if session.get("onboarding_pendente"):
        usuario = get_usuario_sessao()
        return jsonify({
            "status": "onboarding_pendente",
            "senha_definida": usuario.hash_senha is not None,
        }), 200

    if session.get("mfa_pendente"):
        from src.domains.auth.webauthn_2fa import MAX_TENTATIVAS_MFA

        tentativas = session.get("mfa_tentativas", 0)
        tentativas_restantes = max(0, MAX_TENTATIVAS_MFA - tentativas)

        return jsonify({
            "status": "mfa_pendente",
            "metodo": "webauthn",
            "tentativas_restantes": tentativas_restantes,
            # Quando o limite é atingido, não há mais fallback dentro
            # da própria sessão de 2FA -- o usuário precisa voltar ao
            # login e reautenticar do zero, seja por senha (o que
            # reinicia o contador de tentativas) seja por Google (que
            # nunca exige WebAuthn).
            "reautenticar_disponivel": tentativas_restantes == 0,
        }), 200

    return jsonify({"status": "completa"}), 200

@bp_status.get("/me")
@requer_login
def me():
    """Retorna os dados do usuário autenticado na sessão atual e suas configurações. 

    Retorno:
        200 com os dados do usuário.
        401 se a sessão referenciar um usuário que não existe mais
        (nesse caso a sessão também é limpa).
    """
    from src.domains.usuario.repository import UsuarioRepository
    from src.domains.configuracao.service import ConfiguracaoService
    from .webauthn_2fa import carregar_configuracoes
    
    usuario = UsuarioRepository().find_by_id(g.id_usuario)
    
    if not usuario:
        session.clear()
        return json_error("Sessão inválida.", 401)
   
    cfg_service = ConfiguracaoService()
    cfg = cfg_service.obter_ou_criar(usuario.id)
    
    
    
    return json_success(
        data={"usuario": usuario.to_dict(), "configuracoes": cfg.to_dict(), "webauthn": carregar_configuracoes()},
        message="Login realizado com sucesso.",
    )


@bp_status.get("/check-session")
def ck_session():
    from src.core.session import ja_logado
    """Verifica se já existe uma sessão ativa

    
        Retorno:
            200 Se já existe
            401 Se não existe
            
        """
    return ja_logado()