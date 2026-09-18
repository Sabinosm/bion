"""Rotas de login/logout do domínio Auth.

A sessão é lida e escrita via cookie httpOnly. Todo login por senha
exige 2FA em seguida (WebAuthn e/ou TOTP, obrigatórios desde o
onboarding) -- não existe caminho de login sem 2FA. `id_empresa` só é
liberado depois da confirmação via `/webauthn/2fa/confirmar` ou
`/totp/2fa/confirmar` (ver webauthn_2fa.py e totp_2fa.py).

Um reset de senha por admin (ver resetar_senha_usuario em service.py)
não cria um estado separado: zera `hash_senha` e marca
`onboarding_pendente=True`, reaproveitando o branch de onboarding já
existente abaixo. Se o usuário já tem WebAuthn/TOTP confirmados, esses
fatores não são apagados pelo reset -- só a senha; o próximo login cai
em onboarding_pendente (definir senha nova), mas o onboarding libera a
sessão sem pedir escolha de 2FA de novo (ver
onboarding.py::_usuario_tem_algum_2fa_confirmado).
"""

from flask import Blueprint, request, session
from src.core.responses import json_success, json_error
from src.models import db
from src.domains.auth.mfa import metodo_2fa_preferencial, metodos_2fa_disponiveis
from src.domains.auth.onboarding import _usuario_tem_algum_2fa_confirmado
from .services import AuthService

bp = Blueprint("auth", __name__)
_svc = AuthService()


class Login():

    @staticmethod
    @bp.post("/login")
    def login():
        """Autentica um usuário por login e senha.

        A sessão sempre fica pendente de 2FA após autenticar por senha.

        Corpo esperado (JSON ou form): `user_login`, `senha`.

        Retorno:
            200 com `status: mfa_pendente` se autenticado (sempre o
                caso, exceto onboarding pendente).
            200 com `status: onboarding_pendente` se o usuário não tem
                senha definida ainda -- inclusive logo após um reset de
                senha feito por um admin (ver resetar_senha_usuario em
                service.py), que reaproveita este mesmo estado.
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

        # `None` só ocorreria para uma conta legada sem nenhum fator
        # migrado -- o frontend tenta WebAuthn e cai para TOTP
        # normalmente (ver afterLogin.js); se o usuário não tiver
        # nenhum dos dois de verdade, os dois passos falham e o login
        # fica bloqueado -- correto para uma conta inconsistente.
        metodo = metodo_2fa_preferencial(usuario.id)

        session.clear()
        session.permanent = True
        session["id_usuario"] = usuario.id
        # is_admin e funcao_clinica são independentes -- podem ambos
        # ser verdadeiros ao mesmo tempo (admin que também atende). Ver
        # session.py para os decorators que leem cada uma separadamente.
        session["is_admin"] = usuario.is_admin
        session["funcao_clinica"] = usuario.funcao_clinica
        session["uuid_usuario"] = usuario.uuid
        # Necessário para g.is_super_admin (session.py) e para
        # requer_super_admin funcionarem em rotas desta sessão.
        session["is_super_admin"] = usuario.is_super_admin
        # Snapshot da versão da senha NO MOMENTO deste login -- usado
        # por requer_senha_atualizada (session.py) para invalidar
        # sessões cuja senha mudou depois (autotroca ou reset por admin).
        session["senha_versao"] = usuario.senha_versao

        if usuario.onboarding_pendente:
            # Fecha o onboarding aqui mesmo quando os pré-requisitos já
            # estão satisfeitos (senha definida e/ou 2FA confirmado),
            # em vez de depender só de uma chamada separada a
            # /onboarding/concluir ter ocorrido.
            if usuario.hash_senha or _usuario_tem_algum_2fa_confirmado(usuario.id):
                usuario.onboarding_pendente = False
                db.session.commit()
                # segue para o fluxo normal abaixo (mfa_pendente)
            else:
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
