"""
onboarding.py

Rotas de primeiro acesso (onboarding), usadas depois do login por senha ou por
Google enquanto `usuario.onboarding_pendente` for verdadeiro. A conclusão
exige dois requisitos presentes ao mesmo tempo: senha definida e pelo menos
um método de 2FA confirmado, WebAuthn OU TOTP, não os dois. WebAuthn sozinho
seria inviável para parte do público real (notebooks sem Bluetooth são comuns
no parque de clínicas e hospitais); TOTP não tem essa limitação, mas nem todo
usuário o prefere quando já tem um autenticador de plataforma (Windows Hello,
Touch ID).

Este módulo apenas orquestra QUANDO o cadastro de 2FA pode ser feito durante o
onboarding e QUANDO o onboarding pode ser considerado concluído. O cadastro
dos fatores em si (gerar e confirmar o desafio WebAuthn ou o secret TOTP) vive
em webauthn_2fa.py e totp_2fa.py, reaproveitado do fluxo de configurações da
conta. Aqui ficam também a checagem de estado de 2FA e a regra que fecha o
onboarding automaticamente, usada nos logins por senha e por Google.

A sessão só fica completa direto ao concluir o onboarding se o usuário
comprovou a posse de um fator de 2FA nesta própria sessão (cadastrou e
confirmou com assinatura ou código válidos). Quem já tinha fator antes, por
exemplo após um reset de senha feito por admin, termina o onboarding com a
sessão pendente de 2FA e precisa confirmá-lo como em qualquer login.
"""

from flask import Blueprint, request, jsonify, session
from argon2 import PasswordHasher

from src.models import db
from src.core.session import onboarding_pendente_required, get_usuario_sessao, iniciar_mfa_pendente
from src.core.validacoes import validar_senha
from src.domains.auth.mfa import usuario_tem_algum_2fa, metodo_2fa_preferencial, metodos_2fa_disponiveis

bp_onboarding = Blueprint("onboarding", __name__)
ph = PasswordHasher()


def _usuario_tem_algum_2fa_confirmado(id_usuario) -> bool:
    """True se o usuário tem WebAuthn OU TOTP confirmado."""
    return usuario_tem_algum_2fa(id_usuario)


# Chave de sessão: o usuário cadastrou e comprovou um fator de 2FA nesta sessão de onboarding.
FATOR_COMPROVADO_NA_SESSAO = "onboarding_fator_comprovado"


def cadastro_de_fator_permitido(usuario) -> bool:
    """Informa se esta sessão pode cadastrar um fator de 2FA (WebAuthn ou TOTP).

    Fora do onboarding, sempre. Durante o onboarding, só se o usuário ainda não
    tem nenhum fator confirmado ou se já cadastrou um nesta própria sessão.
    Isso impede que quem entrou só com o primeiro fator (ex.: Google) troque ou
    acrescente um fator numa conta que já tinha 2FA, o que permitiria passar
    pelo 2FA com um fator escolhido por quem invadiu.
    """
    if not session.get("onboarding_pendente"):
        return True
    return bool(session.get(FATOR_COMPROVADO_NA_SESSAO)) or not _usuario_tem_algum_2fa_confirmado(usuario.id)


def marcar_fator_comprovado():
    """Registra que o usuário acabou de comprovar a posse de um fator de 2FA durante o onboarding.

    Deve ser chamada só depois de o cadastro ser confirmado com assinatura ou
    código válidos. Sem efeito fora do onboarding.
    """
    if session.get("onboarding_pendente"):
        session[FATOR_COMPROVADO_NA_SESSAO] = True


def onboarding_ainda_pendente(usuario) -> bool:
    """Reavalia o onboarding do usuário no login e informa se ele continua pendente.

    Se `onboarding_pendente` estiver ativo mas o usuário já tem senha E 2FA
    confirmado, a flag é desligada e gravada. Isso evita prender no onboarding
    quem já cumpriu os dois requisitos.

    Exige os dois requisitos, e não apenas um: um reset de senha feito por
    admin zera `hash_senha` mas mantém o 2FA já confirmado, e esse usuário
    precisa ser levado a definir a senha nova.

    Returns:
        True se o onboarding continua pendente, False se não havia pendência
        ou se ela acabou de ser encerrada.
    """
    if not usuario.onboarding_pendente:
        return False

    if usuario.hash_senha and _usuario_tem_algum_2fa_confirmado(usuario.id):
        usuario.onboarding_pendente = False
        db.session.commit()
        return False

    return True


class Onboarding():

    @staticmethod
    @bp_onboarding.route("/definir-senha", methods=["POST"])
    @onboarding_pendente_required
    def definir_senha():
        """Define a senha inicial do usuário, primeiro passo do onboarding.

        Idempotente para quem já tem senha (ex.: cadastrado por um admin):
        não pede senha de novo e só informa que o próximo passo é escolher o
        método de 2FA. Ao definir uma senha nova, o usuário passa a "ativo".

        Corpo esperado (JSON): `senha` (obrigatório só se o usuário ainda não
        tiver `hash_senha`).

        Retorno:
            200 com `status: escolher_2fa` e `id_usuario`, se a senha foi
                definida ou já existia.
            400 com o motivo da invalidação se a senha não passar nas regras.
        """
        usuario = get_usuario_sessao()

        if not usuario.hash_senha:
            dados = request.get_json()
            nova_senha = dados.get("senha")

            senha_valida, resposta = validar_senha(nova_senha)

            if not senha_valida:
                return jsonify(resposta), 400

            usuario.hash_senha = ph.hash(nova_senha)
            usuario.status = "ativo"
            db.session.commit()

        return jsonify({
            "status": "escolher_2fa",
            "id_usuario": usuario.id,
        }), 200

    @staticmethod
    @bp_onboarding.route("/2fa/status", methods=["GET"])
    @onboarding_pendente_required
    def status_2fa():
        """Informa se o usuário já tem algum método de 2FA confirmado.

        O frontend usa a resposta para decidir entre concluir o onboarding e
        mostrar a tela de escolha de método. Só reporta o estado atual, não
        conclui nada.

        Retorno:
            200 com {"tem_2fa": bool}.
        """
        usuario = get_usuario_sessao()
        return jsonify({"tem_2fa": _usuario_tem_algum_2fa_confirmado(usuario.id)}), 200

    @staticmethod
    @bp_onboarding.route("/concluir", methods=["POST"])
    @onboarding_pendente_required
    def concluir_onboarding():
        """Conclui o onboarding, último passo.

        Não cadastra nada: só valida que a senha já foi definida
        (`/definir-senha`) e que ao menos um método de 2FA já foi confirmado
        (`/webauthn/registrar/confirmar` ou `/totp/registrar/confirmar`).
        Desliga `onboarding_pendente` e grava os privilégios de papel na
        sessão (`is_admin`, `funcao_clinica`, `is_super_admin`).

        A sessão só vira completa aqui (grava `id_empresa`) se o usuário
        comprovou um fator nesta sessão. Se o fator já existia antes (ex.:
        reset de senha por admin), a sessão fica em `mfa_pendente` e só vira
        completa depois de o 2FA ser confirmado, como em qualquer login.

        Retorno:
            200 com `status: onboarding_concluido`, `id_usuario` e
                `id_empresa`, se o fator foi comprovado nesta sessão.
            200 com `status: mfa_pendente`, `metodo` e `metodos_disponiveis`,
                se o usuário já tinha fator; o frontend segue para o 2FA.
            400 com `senha_nao_definida` ou `2fa_nao_configurado`, indicando
                ao frontend o passo para o qual voltar.
        """
        usuario = get_usuario_sessao()

        if not usuario.hash_senha:
            return jsonify({"erro": "senha_nao_definida"}), 400

        if not _usuario_tem_algum_2fa_confirmado(usuario.id):
            return jsonify({"erro": "2fa_nao_configurado"}), 400

        usuario.onboarding_pendente = False
        db.session.commit()

        fator_comprovado = bool(session.pop(FATOR_COMPROVADO_NA_SESSAO, None))
        session.pop("onboarding_pendente", None)
        session["is_admin"] = usuario.is_admin
        session["funcao_clinica"] = usuario.funcao_clinica
        session["is_super_admin"] = usuario.is_super_admin

        if not fator_comprovado:
            iniciar_mfa_pendente()
            return jsonify({
                "status": "mfa_pendente",
                "metodo": metodo_2fa_preferencial(usuario.id),
                "metodos_disponiveis": metodos_2fa_disponiveis(usuario.id),
            }), 200

        session["id_empresa"] = usuario.id_empresa

        return jsonify({
            "status": "onboarding_concluido",
            "id_usuario": usuario.id,
            "id_empresa": usuario.id_empresa,
        }), 200