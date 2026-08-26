"""Rotas de login/logout do domínio Auth.

A sessão é lida e escrita via cookie httpOnly. Após autenticar login e
senha, se o usuário tiver credencial WebAuthn cadastrada, a sessão fica
em estado pendente (`mfa_pendente=True`) e `id_empresa` não é liberado
ainda -- a sessão só é promovida a completa após a confirmação via
`/webauthn/2fa/confirmar` (ver `webauthn_2fa.py`).
"""

from flask import Blueprint, request, session
from src.models.usuarios import CredencialWebAuthn
from src.core.responses import json_success, json_error
from .services import AuthService


bp = Blueprint("auth", __name__)
_svc = AuthService()


class Login():
    
    @staticmethod
    @bp.post("/login")
    def login():
        """Autentica um usuário por login e senha.

        Se o usuário tiver WebAuthn cadastrado, deixa a sessão em estado
        pendente de segundo fator em vez de liberá-la por completo.

        Corpo esperado (JSON ou form): `user_login`, `senha`.

        Retorno:
            200 com dados de usuário e configurações se autenticado sem 2FA.
            200 com `status: mfa_pendente` se autenticado mas pendente de 2FA.
            400 se o usuário só tiver login via Google (sem senha).
            401 se as credenciais forem inválidas.
            422 se login ou senha não forem enviados.
        """
        
        data = request.get_json(silent=True) or request.form.to_dict()
        login_val = (data.get("user_login") or "").strip()
        senha = data.get("senha") or ""

        if not login_val or not senha:
            return json_error("Login e senha são obrigatórios.", 422)
        
        usuario, motivo = _svc.autenticar(login_val, senha)
        if motivo == "sem_senha":
            return json_error("Usuário sem senha, faça login pelo Google.", 400)
        if not usuario:
            return json_error("Credenciais inválidas.", 401)

        tem_2fa = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).first() is not None

        session.clear()
        session.permanent = True
        session["id_usuario"] = usuario.id
        session["tipo_usuario"] = usuario.tipo_usuario
        session["uuid_usuario"] = usuario.uuid
        

        if usuario.onboarding_pendente:
            session["onboarding_pendente"] = True
            return json_success(
                data={"status": "onboarding_pendente"},
                message="Cadastro incompleto, finalize o onboarding.",
            )

        if tem_2fa:
            session["mfa_pendente"] = True
            return json_success(
                data={"status": "mfa_pendente", "metodo": "webauthn"},
                message="Confirmação adicional necessária.",
            )
        
        _svc.load(usuario)
        
        return json_success(
            data={"status": "sucess"},
            message="Login realizado com sucesso.",
        )
    
            
    @staticmethod
    @bp.post("/logout")
    def logout():
        """Encerra a sessão atual.

        Retorno:
            200 confirmando o encerramento.
        """
        session.clear()
        return json_success(message="Sessão encerrada.")


