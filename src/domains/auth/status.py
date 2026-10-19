"""
status.py

Rotas informativas sobre o estado da sessão. Diferente de uma checagem que
bloqueia, estas rotas apenas dizem em que estado a sessão está (completa,
com onboarding pendente ou com 2FA pendente) para o frontend decidir para
onde navegar, por exemplo logo após o redirect do Google. As respostas são
sempre JSON, mesmo sendo rotas de apoio à navegação. Também ficam aqui as
rotas que devolvem os dados do usuário da sessão e verificam se há sessão
ativa.
"""

from flask import Blueprint, session, jsonify
from src.core.responses import json_error, json_success
from src.core.session import get_usuario_sessao, requer_login, _mfa_pendente_expirado

bp_status = Blueprint("status", __name__)


def _resposta_se_incompleta():
    """Avalia a sessão e devolve `(resposta, código)` se ela NÃO estiver completa.

    Retorna None quando a sessão está completa, para a rota montar o payload
    final.

    Casos:
        401 `nao_autenticado`: sem sessão iniciada, ou `mfa_pendente` expirado
            (nesse caso a sessão é limpa).
        200 `onboarding_pendente`: inclui `senha_definida`, para o frontend
            saber se pode pular a etapa de senha.
        200 `mfa_pendente`: inclui `metodo` (singular, por compatibilidade),
            `metodos_disponiveis`, `tentativas_restantes` e
            `reautenticar_disponivel`, para o frontend decidir entre tentar de
            novo ou reautenticar por senha ou Google.
    """
    usuario = get_usuario_sessao()
    if not usuario:
        return jsonify({"status": "nao_autenticado"}), 401

    if session.get("onboarding_pendente"):
        return jsonify({
            "status": "onboarding_pendente",
            "senha_definida": usuario.hash_senha is not None,
        }), 200

    if session.get("mfa_pendente"):
        # Expira por tempo fixo (ver _mfa_pendente_expirado em session.py),
        # não só por inatividade do cookie Flask.
        if _mfa_pendente_expirado():
            session.clear()
            return jsonify({"status": "nao_autenticado"}), 401

        from src.domains.auth.mfa import metodos_2fa_disponiveis
        from src.domains.auth.webauthn_2fa import MAX_TENTATIVAS_MFA

        metodos = metodos_2fa_disponiveis(usuario.id)
        restantes = max(0, MAX_TENTATIVAS_MFA - session.get("mfa_tentativas", 0))
        return jsonify({
            "status": "mfa_pendente",
            "metodo": metodos[0] if metodos else None,
            "metodos_disponiveis": metodos,
            "tentativas_restantes": restantes,
            "reautenticar_disponivel": restantes == 0,
        }), 200

    return None


class Status():

    @staticmethod
    @bp_status.get("/status")
    def status_sessao():
        """Estado da sessão, sem exigir autenticação completa e sem dados do usuário.

        `mfa_pendente` ocorre após qualquer login (senha ou Google) enquanto o
        segundo fator ainda não foi confirmado.

        Retorno:
            200 `completa`, `onboarding_pendente` ou `mfa_pendente` (detalhes
                em `_resposta_se_incompleta`).
            401 `nao_autenticado` se não houver sessão iniciada.
        """
        return _resposta_se_incompleta() or (jsonify({"status": "completa"}), 200)

    @staticmethod
    @bp_status.get("/status_completo")
    def status_completo():
        """Igual a `/status`, mas no estado `completa` inclui `usuario`.

        O `usuario` é `to_dict_session()` (uuid, funcao_clinica, is_admin,
        is_super_admin, status). É o que o `watchSession.js` usa para
        reconciliar o perfil e detectar troca de identidade.

        Retorno:
            200 `completa` (com `usuario`), `onboarding_pendente` ou `mfa_pendente`.
            401 `nao_autenticado` se não houver sessão iniciada.
        """
        resposta = _resposta_se_incompleta()
        if resposta:
            return resposta
        return jsonify({
            "status": "completa",
            "usuario": get_usuario_sessao().to_dict_session(),
        }), 200

    @staticmethod
    @bp_status.get("/me")
    @requer_login
    def me():
        """Retorna os dados do usuário da sessão atual, suas configurações e seus dispositivos WebAuthn.

        Exige sessão completa: quem está em onboarding ou com 2FA pendente não recebe dados.

        Retorno:
            200 com `usuario`, `configuracoes` e `webauthn` (lista de credenciais).
            401 se a sessão referenciar um usuário que não existe mais (a
                sessão também é limpa).
        """
        from src.domains.configuracao.service import ConfiguracaoService
        from .webauthn_2fa import carregar_configuracoes

        usuario = get_usuario_sessao()

        if not usuario:
            session.clear()
            return json_error("Sessão inválida.", 401)

        cfg = ConfiguracaoService().obter_ou_criar(usuario.id)

        return json_success(
            data={
                "usuario": usuario.to_dict(),
                "configuracoes": cfg.to_dict(),
                "webauthn": carregar_configuracoes(),
            },
            message="Login realizado com sucesso.",
        )

    @staticmethod
    @bp_status.get("/check-session")
    def ck_session():
        """Verifica se já existe uma sessão ativa.

        Retorno:
            200 se já existe.
            401 se não existe.
        """
        from src.core.session import ja_logado
        return ja_logado()