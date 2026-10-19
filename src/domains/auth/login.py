"""
login.py

Rotas de login e logout por senha do domínio Auth. A sessão é lida e escrita
via cookie httpOnly. Todo login por senha deixa a sessão pendente de segundo
fator (WebAuthn e/ou TOTP, obrigatórios desde o onboarding), e `id_empresa` só
é gravado depois da confirmação em webauthn_2fa.py ou totp_2fa.py. A única
exceção é o onboarding pendente, em que o usuário ainda não tem fator
cadastrado e é levado a concluí-lo primeiro.

Um reset de senha feito por admin não cria um estado separado: zera
`hash_senha` e marca `onboarding_pendente=True`, reaproveitando o ramo de
onboarding deste login. Os fatores de 2FA já confirmados não são apagados pelo
reset; o próximo acesso cai no onboarding para definir a senha nova, sem pedir
a escolha de 2FA de novo.
"""

from flask import Blueprint, request, session
from src.core.responses import json_success, json_error
from src.domains.auth.mfa import metodo_2fa_preferencial, metodos_2fa_disponiveis
from src.domains.auth.onboarding import onboarding_ainda_pendente
from .services import AuthService

bp = Blueprint("auth", __name__)
_svc = AuthService()


class Login():

    @staticmethod
    @bp.post("/login")
    def login():
        """Autentica um usuário por login e senha.

        Reinicia a sessão e grava nela a identidade e os privilégios do
        usuário (`is_admin` e `funcao_clinica` são independentes e podem ser
        ambos verdadeiros), além de `senha_versao`, o snapshot que permite
        invalidar sessões cuja senha mudou depois (autotroca ou reset por
        admin). A sessão sempre fica pendente de 2FA após a senha.

        Corpo esperado (JSON ou form): `user_login`, `senha`.

        Retorno:
            200 com `status: mfa_pendente`, `metodo` (preferencial) e
                `metodos_disponiveis`; é o caso normal. `metodo` pode ser
                None em conta legada sem nenhum fator migrado, e o frontend
                então tenta WebAuthn e cai para TOTP.
            200 com `status: onboarding_pendente` se o usuário ainda não tem
                senha e 2FA definidos, inclusive logo após um reset por admin.
            401 se as credenciais forem inválidas. A resposta é a mesma para
                usuário inexistente, inativo ou sem senha (só Google), para
                não revelar quais contas existem.
            422 se login ou senha não forem enviados.
        """
        data = request.get_json(silent=True) or request.form.to_dict()
        login_val = (data.get("user_login") or "").strip()
        senha = data.get("senha") or ""

        if not login_val or not senha:
            return json_error("Login e senha são obrigatórios.", 422)

        usuario, _ = _svc.autenticar(login_val, senha)

        if not usuario:
            return json_error("Credenciais inválidas.", 401)

        metodo = metodo_2fa_preferencial(usuario.id)

        session.clear()
        session.permanent = True
        session["id_usuario"] = usuario.id
        session["is_admin"] = usuario.is_admin
        session["funcao_clinica"] = usuario.funcao_clinica
        session["uuid_usuario"] = usuario.uuid
        session["is_super_admin"] = usuario.is_super_admin
        session["senha_versao"] = usuario.senha_versao

        if onboarding_ainda_pendente(usuario):
            session["onboarding_pendente"] = True
            return json_success(
                data={"status": "onboarding_pendente"},
                message="Cadastro incompleto, finalize o onboarding.",
            )

        from src.core.session import iniciar_mfa_pendente
        iniciar_mfa_pendente()
        return json_success(
            data={
                "status": "mfa_pendente",
                "metodo": metodo,
                "metodos_disponiveis": metodos_2fa_disponiveis(usuario.id),
            },
            message="Confirmação adicional necessária.",
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