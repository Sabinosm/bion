"""Rotas de primeiro acesso (onboarding).

Chamadas depois do login (via senha ou Google) quando
`usuario.onboarding_pendente == True`. Fluxo: 1) definir senha, 2)
sessão completa é liberada.

WebAuthn não faz mais parte do onboarding
-------------------------------------------
O cadastro de credencial WebAuthn foi movido para fora deste fluxo --
passa a ser feito depois, nas configurações da conta, com o usuário
já em sessão completa. Isso reduz o atrito do primeiro acesso: só a
senha é exigida para liberar a sessão. Quem quiser usar WebAuthn
como segundo fator no login por senha pode cadastrá-lo quando
quiser, nas configurações; até lá, login por senha simplesmente não
pede 2FA (sem credencial cadastrada, não há o que confirmar -- ver
login.py).

A rota de cadastro de WebAuthn em si (reaproveitando as mesmas
funções do fluxo antigo) deve ser implementada no domínio de
configurações, usando `requer_login` no lugar de
`onboarding_pendente_required`.
"""

from flask import Blueprint, request, jsonify, session
from argon2 import PasswordHasher

from src.models import db
from src.models.usuarios import Usuario
from src.core.session import onboarding_pendente_required, get_usuario_sessao
from src.core.validacoes import validar_senha

bp_onboarding = Blueprint("onboarding", __name__)
ph = PasswordHasher()

class Onboarding():
    
    @staticmethod
    @bp_onboarding.route("/definir-senha", methods=["POST"])
    @onboarding_pendente_required
    def definir_senha():
        """Define a senha inicial do usuário e conclui o onboarding.

        Único passo do onboarding: ao definir a senha com sucesso, marca
        `onboarding_pendente = False` e libera a sessão completa (define
        `id_empresa`). O cadastro de WebAuthn não é mais parte deste
        fluxo -- fica disponível depois, nas configurações da conta.

        Corpo esperado (JSON): `senha`.

        Retorno:
            200 com status `onboarding_concluido` e os IDs de usuário/empresa,
            tanto se a senha acabou de ser definida quanto se o usuário já
            tinha senha definida (idempotente, ex.: cadastrado por admin).
            400 com o motivo da invalidação se a senha não passar nas regras.
        """
        usuario = get_usuario_sessao()

        if not usuario.hash_senha:
            dados = request.get_json()
            nova_senha = dados.get("senha")

            senha_valida, resposta = validar_senha(nova_senha)

            if senha_valida == False:
                return jsonify(resposta), 400

            usuario.hash_senha = ph.hash(nova_senha)
            usuario.onboarding_pendente = False
            usuario.status="ativo"

        db.session.commit()

        session.pop("onboarding_pendente", None)
        session["id_empresa"] = usuario.id_empresa

        return jsonify({
            "status": "onboarding_concluido",
            "id_usuario": usuario.id,
            "id_empresa": usuario.id_empresa,
        }), 200