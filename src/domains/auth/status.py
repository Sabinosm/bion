"""Rota informativa de status de sessão.

Diferente de `/auth/me`, esta rota não bloqueia -- apenas informa em
que estado a sessão está. Usada pela página pós-login logo após o
redirect do Google, para decidir se o usuário deve ir para onboarding,
confirmação de 2FA, ou dashboard. Mantém o contrato de resposta somente
em JSON, mesmo sendo uma rota de apoio à navegação.
"""

from flask import Blueprint, session, jsonify, g
from src.core.responses import json_error, json_success
from src.core.session import requer_login, get_usuario_sessao, _mfa_pendente_expirado

bp_status = Blueprint("status", __name__)

def _resposta_se_incompleta():
        """Devolve (resposta, código) se a sessão não estiver completa; senão None."""
        usuario = get_usuario_sessao()
        if not usuario:
            return jsonify({"status": "nao_autenticado"}), 401

        if session.get("onboarding_pendente"):
            return jsonify({
                "status": "onboarding_pendente",
                "senha_definida": usuario.hash_senha is not None,
            }), 200

        if session.get("mfa_pendente"):
            if _mfa_pendente_expirado():
                session.clear()
                return jsonify({"status": "nao_autenticado"}), 401

            from src.domains.auth.mfa import metodos_2fa_disponiveis
            from src.domains.auth.webauthn_2fa import MAX_TENTATIVAS_MFA

            metodos = metodos_2fa_disponiveis(usuario.id)
            restantes = max(0, MAX_TENTATIVAS_MFA - session.get("mfa_tentativas", 0))
            return jsonify({
                "status": "mfa_pendente",
                "metodo": metodos[0] if metodos else None,  # compatibilidade
                "metodos_disponiveis": metodos,
                "tentativas_restantes": restantes,
                "reautenticar_disponivel": restantes == 0,
            }), 200

        return None
    
class Status():

    @staticmethod
    @bp_status.route("/status", methods=["GET"])
    def status_sessao():
        """Estado da sessão, sem dados do usuário."""
        return _resposta_se_incompleta() or (jsonify({"status": "completa"}), 200)

    @staticmethod
    @bp_status.get("/me")
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

    @bp_status.get("/status_completo")
    def status_completo():
        """Estado da sessão; quando `completa`, inclui `usuario` (to_dict_session)."""
        resposta = _resposta_se_incompleta()
        if resposta:
            return resposta
        return jsonify({
            "status": "completa",
            "usuario": get_usuario_sessao().to_dict_session(),
        }), 200
        
    
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
