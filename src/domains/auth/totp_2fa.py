"""
totp_2fa.py

TOTP (código de 6 dígitos de um app autenticador) como segundo fator
alternativo ao WebAuthn. É uma das duas opções, WebAuthn OU TOTP, que o
onboarding exige escolher, e ambas continuam disponíveis depois nas
configurações da conta. Espelha a estrutura de webauthn_2fa.py: rotas e
lógica numa classe só, sem service nem repository próprios.

Onde entra no login: o WebAuthn é tentado primeiro, se o usuário tiver
credencial (até o limite de tentativas definido em webauthn_2fa.py); sem
credencial, ou esgotadas as tentativas, o frontend chama o TOTP. Se o TOTP
também esgotar, ou o usuário não tiver nenhum fator, não há fallback para
Google sem 2FA: todo login exige 2FA, e esgotar os dois métodos é tratado
como bloqueio, em que o frontend orienta contato com o administrador.

Onde entra no step-up (reconfirmação antes de ação sensível): o WebAuthn é
tentado primeiro, se existir; depois o TOTP, vinculado a uma `acao` em vez de
a um login. Esgotado o TOTP, ou sem nenhum dos dois fatores, cai no fallback
senha mais Google, mantido no step-up (o racional dessa diferença para o login
está em step_up.py).

Limite de tentativas: diferente do WebAuthn, onde uma falha costuma ser "sem
autenticador disponível", um código TOTP errado pode ser tentativa de
adivinhação, já que são só 6 dígitos. Por isso o limite é deliberadamente
baixo, vive na sessão e zera a cada novo login ou step-up iniciado, no mesmo
padrão do contador do WebAuthn.
"""

from flask import Blueprint, request, jsonify, session

import pyotp

from src.models import db
from src.models.usuarios.credencial_totp import CredencialTOTP
from src.models.usuarios.credencial_webauthn import CredencialWebAuthn
from src.core.session import (
    mfa_pendente_required,
    get_id_usuario_sessao,
    requer_login,
    get_usuario_sessao,
    requer_login_ou_onboarding_pendente,
)
from src.domains.auth.webauthn_config import RP_NAME
from src.domains.auth.onboarding import cadastro_de_fator_permitido, marcar_fator_comprovado

bp_totp_2fa = Blueprint("totp_2fa", __name__)

MAX_TENTATIVAS_TOTP = 5


def _credencial_confirmada(id_usuario):
    """TOTP já confirmado do usuário, ou None."""
    return CredencialTOTP.query.filter_by(id_usuario=id_usuario, confirmado=True).first()


def _codigo_totp_valido(secret: str, codigo: str) -> bool:
    """True se o código bate com o secret, aceitando uma janela de 30s para cada lado."""
    return bool(codigo) and pyotp.TOTP(secret).verify(codigo, valid_window=1)


def resetar_tentativas_stepup_totp(acao: str) -> int:
    """Zera o contador de tentativas do step-up TOTP e vincula a `acao` na sessão.

    Grava `stepup_totp_tentativas` e `stepup_totp_acao`. Existe separada de
    `stepup_totp_iniciar` para ser reusada por `stepup_iniciar` (step_up.py)
    quando o método já foi decidido como TOTP, evitando que o frontend chame
    `/totp/2fa/stepup/iniciar` só para obter o mesmo reset.

    Returns:
        tentativas_restantes, sempre MAX_TENTATIVAS_TOTP, pois acabou de zerar.
    """
    session["stepup_totp_tentativas"] = 0
    session["stepup_totp_acao"] = acao
    return MAX_TENTATIVAS_TOTP


class Totp():

    # ------------------------------------------------------------------
    # Cadastro (sessão completa ou onboarding)
    # ------------------------------------------------------------------

    @staticmethod
    @bp_totp_2fa.post("/registrar/iniciar")
    @requer_login_ou_onboarding_pendente
    def registrar_totp_iniciar():
        """Gera um novo secret TOTP (ainda não confirmado) e devolve a URI otpauth://.

        O frontend renderiza a URI como QR code. Aceita sessão completa
        (configurações da conta) ou em onboarding_pendente.

        O secret novo NUNCA é gravado no banco aqui: fica só na sessão
        (`totp_secret_pendente`), como o desafio de um WebAuthn em andamento,
        efêmero e descartado se nunca for confirmado. Assim, chamar esta rota
        de novo não invalida um TOTP já confirmado e em uso. A linha de
        CredencialTOTP só é tocada em `/registrar/confirmar`, e só se o código
        bater.

        Retorno:
            200 com {"otpauth_uri": "...", "secret_texto": "..."}.
            `secret_texto` serve para digitação manual caso o QR não possa ser
            escaneado, e só é devolvido nesta etapa: depois de confirmado, o
            secret nunca mais é exposto por nenhuma rota.
            403 se o cadastro de fator não for permitido no onboarding (ver
                `cadastro_de_fator_permitido` em onboarding.py).
        """
        usuario = get_usuario_sessao()

        if not cadastro_de_fator_permitido(usuario):
            return jsonify({"erro": "cadastro_de_fator_nao_permitido"}), 403

        secret = pyotp.random_base32()
        session["totp_secret_pendente"] = secret

        otpauth_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=usuario.email,
            issuer_name=RP_NAME,
        )

        return jsonify({
            "otpauth_uri": otpauth_uri,
            "secret_texto": secret,
        }), 200

    @staticmethod
    @bp_totp_2fa.post("/registrar/confirmar")
    @requer_login_ou_onboarding_pendente
    def registrar_totp_confirmar():
        """Confirma o cadastro exigindo o primeiro código válido do secret pendente.

        Único lugar que cria ou substitui a credencial no banco, e só depois
        de o código bater: até lá, um TOTP já confirmado continua sendo o
        válido. A troca do secret e `confirmado=True` acontecem juntas, então
        nunca existe um instante em que `confirmado=False` aponta para o fator
        antigo já descartado.

        Corpo esperado (JSON): {"codigo": "123456"}.

        Retorno:
            200 com {"totp": {...}} se o código bater.
            400 se faltar o código, não houver cadastro pendente ou o código
                for inválido.
            403 se o cadastro de fator não for permitido no onboarding.
        """
        usuario = get_usuario_sessao()

        if not cadastro_de_fator_permitido(usuario):
            return jsonify({"erro": "cadastro_de_fator_nao_permitido"}), 403

        dados = request.get_json(silent=True) or {}
        codigo = (dados.get("codigo") or "").strip()

        if not codigo:
            return jsonify({"erro": "codigo_obrigatorio"}), 400

        secret_pendente = session.get("totp_secret_pendente")
        if not secret_pendente:
            return jsonify({"erro": "cadastro_nao_iniciado"}), 400

        if not _codigo_totp_valido(secret_pendente, codigo):
            return jsonify({"erro": "codigo_invalido"}), 400

        credencial = CredencialTOTP.query.filter_by(id_usuario=usuario.id).first()
        if not credencial:
            credencial = CredencialTOTP(id_usuario=usuario.id)
            db.session.add(credencial)

        credencial.definir_secret(secret_pendente)
        credencial.confirmado = True
        db.session.commit()

        marcar_fator_comprovado()
        session.pop("totp_secret_pendente", None)

        return jsonify({"totp": credencial.to_dict()}), 200

    @staticmethod
    @bp_totp_2fa.delete("/remover")
    @requer_login
    def remover_totp():
        """Remove o TOTP cadastrado do usuário logado.

        Só é permitido se o usuário TAMBÉM tiver 1+ credencial WebAuthn:
        do contrário ficaria sem 2FA algum, o que não é permitido.

        Retorno:
            200 com {"status": "removido"}.
            404 se não houver TOTP cadastrado.
            409 se for o único fator de 2FA do usuário.
        """
        usuario = get_usuario_sessao()

        credencial = CredencialTOTP.query.filter_by(id_usuario=usuario.id).first()
        if not credencial:
            return jsonify({"erro": "totp_nao_cadastrado"}), 404

        tem_webauthn = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).first() is not None
        if not tem_webauthn:
            return jsonify({"erro": "ultimo_fator_nao_pode_ser_removido"}), 409

        db.session.delete(credencial)
        db.session.commit()

        return jsonify({"status": "removido"}), 200

    # ------------------------------------------------------------------
    # Segundo fator no login (sessão em mfa_pendente)
    # ------------------------------------------------------------------

    @staticmethod
    @bp_totp_2fa.post("/2fa/iniciar")
    @mfa_pendente_required
    def segundo_fator_totp_iniciar():
        """Confirma que o usuário tem TOTP disponível e zera o contador de tentativas do TOTP.

        Não gera "desafio" (TOTP não usa challenge/response como o WebAuthn).
        Existe para o frontend confirmar que o método está disponível antes de
        mostrar o campo de código, e para reiniciar `totp_tentativas` de forma
        explícita a cada nova tentativa de login.

        Retorno:
            200 com {"metodo": "totp", "tentativas_restantes": ...} se o
                usuário tiver TOTP confirmado.
            400 se não tiver.
        """
        if not _credencial_confirmada(get_id_usuario_sessao()):
            return jsonify({"erro": "totp_nao_cadastrado"}), 400

        session["totp_tentativas"] = 0

        return jsonify({
            "metodo": "totp",
            "tentativas_restantes": MAX_TENTATIVAS_TOTP,
        }), 200

    @staticmethod
    @bp_totp_2fa.post("/2fa/confirmar")
    @mfa_pendente_required
    def segundo_fator_totp_confirmar():
        """Valida o código TOTP e promove a sessão a completa.

        Mesmo efeito final de `segundo_fator_confirmar` em webauthn_2fa.py,
        pela mesma chamada centralizada em `AuthService.liberar_sessao_completa`.

        Corpo esperado (JSON): {"codigo": "123456"}.

        Retorno:
            200 com `id_usuario`, `email` e `id_empresa` se o código for válido.
            400 se o usuário não tiver TOTP confirmado.
            401 com `sessao_invalida` se o usuário foi desativado nesse meio-tempo.
            401 com `tentativas_restantes` se o código for inválido.
            429 se as tentativas de TOTP desta sessão se esgotarem. É o fim
                da linha no login (diferente do step-up): não há fallback para
                Google sem 2FA. Se o WebAuthn já tinha esgotado antes, o
                usuário não tem mais método nesta tentativa, e o frontend deve
                mostrar um estado de bloqueio orientando contato com o
                administrador.
        """
        id_usuario = get_id_usuario_sessao()

        tentativas = session.get("totp_tentativas", 0)
        if tentativas >= MAX_TENTATIVAS_TOTP:
            return jsonify({
                "erro": "limite_tentativas_excedido",
                "tentativas_restantes": 0,
            }), 429

        dados = request.get_json(silent=True) or {}
        codigo = (dados.get("codigo") or "").strip()

        credencial = _credencial_confirmada(id_usuario)
        if not credencial:
            return jsonify({"erro": "totp_nao_cadastrado"}), 400

        if not _codigo_totp_valido(credencial.secret_plano, codigo):
            tentativas += 1
            session["totp_tentativas"] = tentativas
            return jsonify({
                "erro": "codigo_invalido",
                "tentativas_restantes": max(0, MAX_TENTATIVAS_TOTP - tentativas),
            }), 401

        from src.domains.usuario.repository import UsuarioRepository
        from src.domains.auth.services import AuthService
        usuario = UsuarioRepository().find_by_id(id_usuario)

        if not AuthService().liberar_sessao_completa(usuario, db):
            return jsonify({"erro": "sessao_invalida"}), 401

        return jsonify({
            "id_usuario": usuario.id,
            "email": usuario.email,
            "id_empresa": usuario.id_empresa,
        }), 200

    # ------------------------------------------------------------------
    # Segundo fator no step-up (sessão completa, vínculo com a ação)
    # ------------------------------------------------------------------

    @staticmethod
    @bp_totp_2fa.post("/2fa/stepup/iniciar")
    @requer_login
    def stepup_totp_iniciar():
        """Confirma TOTP disponível para o step-up da `acao` e zera o contador deste fluxo.

        Não usa `mfa_pendente`: é uma rota de sessão completa, vinculada à
        ação, como as de step_up.py.

        Corpo esperado (JSON): {"acao": "..."}.

        Retorno:
            200 com `metodo: "totp"`, `acao` e `tentativas_restantes`.
            400 se `acao` não for informada ou não houver TOTP confirmado.
        """
        dados = request.get_json(silent=True) or {}
        acao = dados.get("acao")
        if not acao:
            return jsonify({"erro": "acao_nao_especificada"}), 400

        if not _credencial_confirmada(get_id_usuario_sessao()):
            return jsonify({"erro": "totp_nao_cadastrado"}), 400

        return jsonify({
            "metodo": "totp",
            "acao": acao,
            "tentativas_restantes": resetar_tentativas_stepup_totp(acao),
        }), 200

    @staticmethod
    @bp_totp_2fa.post("/2fa/stepup/confirmar")
    @requer_login
    def stepup_totp_confirmar():
        """Valida o código TOTP e emite um token de step-up.

        Mesmo formato de `stepup_confirmar` (WebAuthn) em step_up.py, pelo
        mesmo emissor de token, que alimenta `requer_confirmacao_recente`.

        Corpo esperado (JSON): {"acao": "...", "codigo": "123456"}.

        Retorno:
            200 com `token_confirmacao`, `acao` e `expira_em_segundos`.
            400 se o usuário não tiver TOTP confirmado.
            401 se a ação não corresponder à iniciada, ou o código for
                inválido (neste caso com `tentativas_restantes`).
            429 se as tentativas se esgotarem. Diferente do login, não é fim
                de linha: o frontend deve cair para o fallback senha mais
                Google, sem mostrar bloqueio nem oferecer "tentar outro método".
        """
        dados = request.get_json(silent=True) or {}
        acao = dados.get("acao")
        codigo = (dados.get("codigo") or "").strip()

        if not acao or acao != session.get("stepup_totp_acao"):
            return jsonify({"erro": "acao_nao_corresponde_ao_desafio"}), 401

        id_usuario = get_id_usuario_sessao()

        tentativas = session.get("stepup_totp_tentativas", 0)
        if tentativas >= MAX_TENTATIVAS_TOTP:
            return jsonify({
                "erro": "limite_tentativas_excedido",
                "tentativas_restantes": 0,
            }), 429

        credencial = _credencial_confirmada(id_usuario)
        if not credencial:
            return jsonify({"erro": "totp_nao_cadastrado"}), 400

        if not _codigo_totp_valido(credencial.secret_plano, codigo):
            tentativas += 1
            session["stepup_totp_tentativas"] = tentativas
            return jsonify({
                "erro": "codigo_invalido",
                "tentativas_restantes": max(0, MAX_TENTATIVAS_TOTP - tentativas),
            }), 401

        session.pop("stepup_totp_tentativas", None)
        session.pop("stepup_totp_acao", None)

        from src.domains.auth.step_up import _emitir_token, DURACAO_TOKEN_SEGUNDOS

        token = _emitir_token(id_usuario, acao)

        return jsonify({
            "token_confirmacao": token,
            "acao": acao,
            "expira_em_segundos": DURACAO_TOKEN_SEGUNDOS,
        }), 200