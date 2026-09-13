"""Rotas de primeiro acesso (onboarding).

Chamadas depois do login (via senha ou Google) quando
`usuario.onboarding_pendente == True`.

ALTERADO (2FA sempre obrigatório -- ver mfa.py, login.py, oauth.py):
o onboarding volta a ter DOIS passos, não um só:
  1) definir senha (`/definir-senha`, sem mudança de comportamento
     aqui além do que já existia);
  2) escolher e confirmar pelo menos um método de 2FA -- WebAuthn OU
     TOTP (`/2fa/escolher`) -- antes de `onboarding_pendente` virar
     False e a sessão ser liberada por completo.

Isso reverte a decisão anterior deste módulo (WebAuthn fora do
onboarding, cadastrável só depois nas configurações) porque login sem
2FA algum deixou de existir no sistema -- se o onboarding liberasse a
sessão sem nenhum fator cadastrado, o usuário nunca mais conseguiria
logar de novo (login.py e oauth.py agora exigem WebAuthn/TOTP sempre).

Por que ainda é uma ESCOLHA (não WebAuthn obrigatório fixo)
----------------------------------------------------------------
WebAuthn sozinho é inviável para boa parte do público real deste
sistema (notebooks sem Bluetooth, comum no parque de hardware de
clínicas/hospitais no Brasil -- ver discussão de produto). TOTP não
tem essa limitação (só depende de um celular com relógio certo e um
app gratuito), mas nem todo usuário necessariamente prefere TOTP se
já tiver um authenticator de plataforma disponível (Windows Hello,
Touch ID). Por isso o onboarding oferece as duas opções e exige só
UMA delas -- não as duas -- para não impor o mesmo problema de
inviabilidade que motivou originalmente tirar o WebAuthn obrigatório
do onboarding.

As rotas de cadastro em si (gerar desafio WebAuthn / gerar secret
TOTP e confirmar) continuam vivendo em webauthn_2fa.py e totp_2fa.py
-- este módulo só orquestra QUANDO elas podem ser chamadas durante o
onboarding e quando o onboarding pode ser considerado concluído.
"""

from flask import Blueprint, request, jsonify, session
from argon2 import PasswordHasher

from src.models import db
from src.models.usuarios.credencial_totp import CredencialTOTP
from src.models.usuarios.credencial_webauthn import CredencialWebAuthn
from src.core.session import onboarding_pendente_required, get_usuario_sessao
from src.core.validacoes import validar_senha

bp_onboarding = Blueprint("onboarding", __name__)
ph = PasswordHasher()

class Onboarding():
    
    @staticmethod
    @bp_onboarding.route("/definir-senha", methods=["POST"])
    @onboarding_pendente_required
    def definir_senha():
        """Define a senha inicial do usuário -- PRIMEIRO passo do
        onboarding, não conclui mais sozinho.

        ALTERADO: antes, definir a senha já liberava a sessão completa
        (`id_empresa` definido, `onboarding_pendente = False`). Agora
        isso só acontece depois que o usuário também escolher e
        confirmar um método de 2FA -- ver `/2fa/escolher` abaixo. Esta
        rota continua idempotente para quem já tem senha definida (ex:
        cadastrado por admin): não pede senha de novo, só informa que o
        próximo passo é a escolha do método de 2FA.

        Corpo esperado (JSON): `senha` (obrigatório só se o usuário
        ainda não tiver hash_senha).

        Retorno:
            200 com `status: escolher_2fa` -- a senha foi definida (ou
            já existia) e o onboarding ainda não está concluído; o
            frontend deve seguir para a tela de escolha de método.
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
        """Informa se o usuário já tem algum método de 2FA confirmado
        -- usado pelo frontend para decidir se pode concluir o
        onboarding ou ainda precisa mostrar a tela de escolha.

        Não conclui nada sozinho -- só reporta o estado atual. Útil
        também para o caso idempotente (usuário já tinha senha e/ou
        2FA de uma sessão anterior que não terminou de concluir).

        Retorno:
            200 com {"tem_2fa": bool}.
        """
        usuario = get_usuario_sessao()
        tem_2fa = _usuario_tem_algum_2fa_confirmado(usuario.id)
        return jsonify({"tem_2fa": tem_2fa}), 200

    @staticmethod
    @bp_onboarding.route("/concluir", methods=["POST"])
    @onboarding_pendente_required
    def concluir_onboarding():
        """Conclui o onboarding e libera a sessão completa -- SEGUNDO e
        último passo, chamado depois que a senha já foi definida
        (/definir-senha) e pelo menos um método de 2FA já foi
        confirmado (via /webauthn/registrar/confirmar ou
        /totp/registrar/confirmar, ambos reaproveitados do fluxo de
        configurações -- ver webauthn_2fa.py e totp_2fa.py).

        Esta rota não cadastra nada, só valida que os pré-requisitos
        foram cumpridos e, se sim, libera a sessão -- mesmo papel que
        definir_senha() cumpria sozinho antes desta mudança.

        Retorno:
            200 com status `onboarding_concluido` e os IDs de
            usuário/empresa, se senha e 2FA já estiverem prontos.
            400 com `senha_nao_definida` se a senha ainda não foi
            definida, ou `2fa_nao_configurado` se nenhum método de 2FA
            foi confirmado ainda -- o frontend deve voltar para o
            passo correspondente, não deveria conseguir chegar aqui
            fora de ordem numa navegação normal.
        """
        usuario = get_usuario_sessao()

        if not usuario.hash_senha:
            return jsonify({"erro": "senha_nao_definida"}), 400

        if not _usuario_tem_algum_2fa_confirmado(usuario.id):
            return jsonify({"erro": "2fa_nao_configurado"}), 400

        usuario.onboarding_pendente = False
        db.session.commit()

        session.pop("onboarding_pendente", None)
        session["id_empresa"] = usuario.id_empresa

        return jsonify({
            "status": "onboarding_concluido",
            "id_usuario": usuario.id,
            "id_empresa": usuario.id_empresa,
        }), 200


def _usuario_tem_algum_2fa_confirmado(id_usuario) -> bool:
    """Mesma checagem de mfa.py::usuario_tem_algum_2fa, reimplementada
    aqui em vez de importada para não criar uma dependência cruzada
    entre onboarding.py e mfa.py por causa de uma checagem trivial de
    2 queries -- mfa.py é especificamente sobre decidir método de
    login/step-up, não sobre onboarding. Se essa duplicação incomodar
    no futuro, mover ambas para um módulo comum de "estado de 2FA do
    usuário" é uma refatoração segura.
    """
    tem_webauthn = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).first() is not None
    if tem_webauthn:
        return True
    return CredencialTOTP.query.filter_by(
        id_usuario=id_usuario, confirmado=True
    ).first() is not None