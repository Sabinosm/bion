"""TOTP como segundo fator alternativo ao WebAuthn.

ALTERADO (2FA sempre obrigatório -- ver mfa.py, login.py, oauth.py,
onboarding.py): TOTP deixou de ser um fator "extra" que só importava
com WebAuthn já cadastrado -- agora é uma das duas opções (WebAuthn OU
TOTP) que o onboarding exige escolher, e ambas continuam disponíveis
depois via configurações da conta.

Espelha a estrutura de webauthn_2fa.py (mesmo estilo: rotas e lógica
numa classe só, sem Service/Repository próprios).

Onde este módulo entra no fluxo (login e step-up)
----------------------------------------------------
Login (webauthn_2fa.py, segundo_fator_iniciar/confirmar):
  1. WebAuthn é tentado primeiro, SE o usuário tiver credencial
     cadastrada (até MAX_TENTATIVAS_MFA, em webauthn_2fa.py). Se não
     tiver nenhuma, pula direto para TOTP.
  2. Se WebAuthn esgotar as tentativas (ou não estiver disponível), o
     FRONTEND chama TOTP como próximo método -- ver `/totp/2fa/iniciar`
     e `/totp/2fa/confirmar` abaixo.
  3. ALTERADO: se TOTP também esgotar (ou o usuário não tiver
     nenhum), NÃO HÁ MAIS fallback para Google sem 2FA -- todo login
     (por senha ou Google, ver oauth.py) exige 2FA sempre. Esgotar os
     dois métodos é tratado como bloqueio: o frontend deve orientar
     contato com o administrador, não redirecionar para um caminho
     sem 2FA (esse caminho não existe mais no sistema).

Step-up (step_up.py, stepup_iniciar/confirmar):
  1. WebAuthn é tentado primeiro, se o usuário tiver.
  2. Se não tiver ou esgotar, o frontend chama TOTP
     (`/totp/2fa/stepup/iniciar` e `/totp/2fa/stepup/confirmar`
     abaixo), vinculado a uma `acao` de step-up em vez de login.
  3. Se TOTP também esgotar (ou o usuário não tiver nenhum dos dois):
     cai no fallback senha+Google (mantido no step-up -- diferente do
     login, ver docstring de step_up.py para o racional dessa
     diferença).

Limite de tentativas
---------------------
Diferente do WebAuthn (onde uma tentativa falha tipicamente por "sem
autenticador disponível", não por força bruta), um código TOTP errado
pode ser tentativa de adivinhação -- são só 6 dígitos. Por isso
`MAX_TENTATIVAS_TOTP` é deliberadamente baixo (5) e conta na sessão,
resetando a cada novo login/step-up iniciado -- mesmo padrão de
`mfa_tentativas` em webauthn_2fa.py.
"""

from flask import Blueprint, request, jsonify, session

import pyotp

from src.models import db
from src.models.usuarios.credencial_totp import CredencialTOTP
from src.core.session import mfa_pendente_required, get_id_usuario_sessao, requer_login, get_usuario_sessao, requer_login_ou_onboarding_pendente
from src.domains.auth.webauthn_config import RP_NAME

bp_totp_2fa = Blueprint("totp_2fa", __name__)

MAX_TENTATIVAS_TOTP = 5


class Totp():

    # ============================================
    # Cadastro (sessão completa, @requer_login -- mesmo padrão de
    # registrar_dispositivo_iniciar/confirmar em webauthn_2fa.py)
    # ============================================

    @staticmethod
    @bp_totp_2fa.post("/registrar/iniciar")
    @requer_login_ou_onboarding_pendente
    def registrar_totp_iniciar():
        """Gera um novo secret TOTP (ainda não confirmado) e devolve a
        URI otpauth:// para o frontend renderizar como QR code.

        ALTERADO: aceita tanto sessão completa (configurações da
        conta) quanto sessão em onboarding_pendente (ver
        onboarding.py, que reintroduziu a escolha obrigatória de
        WebAuthn/TOTP) -- ver requer_login_ou_onboarding_pendente em
        session.py.

        Diferente do WebAuthn, não há "excluir credenciais existentes"
        -- se o usuário já tiver um CredencialTOTP (confirmado ou
        não), este endpoint SUBSTITUI o secret anterior (mesma linha,
        novo secret, `confirmado` volta a False). Só faz sentido ter 1
        TOTP ativo por usuário -- reconfigurar substitui, não acumula.

        Retorno:
            200 com {"otpauth_uri": "...", "secret_texto": "..."}.
            `secret_texto` é devolvido só nesta etapa (para o usuário
            digitar manualmente caso não consiga escanear o QR) --
            depois de confirmado, o secret nunca mais é exposto por
            nenhuma rota.
        """
        usuario = get_usuario_sessao()

        secret = pyotp.random_base32()

        credencial = CredencialTOTP.query.filter_by(id_usuario=usuario.id).first()
        if not credencial:
            credencial = CredencialTOTP(id_usuario=usuario.id)
            db.session.add(credencial)

        credencial.definir_secret(secret)
        credencial.confirmado = False
        db.session.commit()

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
        """Confirma que o usuário conseguiu configurar o secret
        corretamente, exigindo o primeiro código válido antes de
        marcar `confirmado=True`.

        Corpo esperado (JSON): {"codigo": "123456"}.

        Retorno:
            200 com {"totp": {...}} se o código bater.
            400 se não houver registro pendente ou o código for inválido.
        """
        usuario = get_usuario_sessao()
        dados = request.get_json(silent=True) or {}
        codigo = (dados.get("codigo") or "").strip()

        if not codigo:
            return jsonify({"erro": "codigo_obrigatorio"}), 400

        credencial = CredencialTOTP.query.filter_by(id_usuario=usuario.id).first()
        if not credencial:
            return jsonify({"erro": "cadastro_nao_iniciado"}), 400

        totp = pyotp.TOTP(credencial.secret_plano)
        if not totp.verify(codigo, valid_window=1):
            return jsonify({"erro": "codigo_invalido"}), 400

        credencial.confirmado = True
        db.session.commit()

        return jsonify({"totp": credencial.to_dict()}), 200

    @staticmethod
    @bp_totp_2fa.delete("/remover")
    @requer_login
    def remover_totp():
        """Remove o TOTP cadastrado do usuário logado.

        ALTERADO (2FA sempre obrigatório -- bloqueio simétrico ao de
        remover_credencial em webauthn_2fa.py): diferente da versão
        anterior deste método (que nunca bloqueava, pois WebAuthn era
        tratado como obrigatório em separado), agora a remoção só é
        permitida se o usuário TAMBÉM tiver 1+ credencial WebAuthn
        cadastrada -- do contrário, ficaria sem 2FA algum, o que não é
        mais permitido (login sempre exige 2FA).

        Retorno:
            200 confirmando a remoção.
            404 se não houver TOTP cadastrado.
            409 se for o único fator de 2FA do usuário (sem WebAuthn
                como alternativa).
        """
        usuario = get_usuario_sessao()

        credencial = CredencialTOTP.query.filter_by(id_usuario=usuario.id).first()
        if not credencial:
            return jsonify({"erro": "totp_nao_cadastrado"}), 404

        from src.models.usuarios import CredencialWebAuthn
        tem_webauthn = CredencialWebAuthn.query.filter_by(id_usuario=usuario.id).first() is not None
        if not tem_webauthn:
            return jsonify({"erro": "ultimo_fator_nao_pode_ser_removido"}), 409

        db.session.delete(credencial)
        db.session.commit()

        return jsonify({"status": "removido"}), 200

    # ============================================
    # Segundo fator -- LOGIN (chamado só depois de WebAuthn esgotar
    # tentativas em /webauthn/2fa/iniciar; sessão em mfa_pendente)
    # ============================================

    @staticmethod
    @bp_totp_2fa.post("/2fa/iniciar")
    @mfa_pendente_required
    def segundo_fator_totp_iniciar():
        """Confirma que o usuário tem TOTP disponível como próximo
        método, e reseta o contador de tentativas específico do TOTP.

        Não gera "desafio" (TOTP não usa challenge/response como
        WebAuthn) -- existe só para o frontend confirmar que o método
        está disponível antes de mostrar o campo de código, e para
        reiniciar `totp_tentativas` de forma explícita a cada nova
        tentativa de login.

        Retorno:
            200 se o usuário tiver TOTP confirmado.
            400 se não tiver.
        """
        id_usuario = get_id_usuario_sessao()

        credencial = CredencialTOTP.query.filter_by(
            id_usuario=id_usuario, confirmado=True
        ).first()
        if not credencial:
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
        """Valida o código TOTP e promove a sessão a completa -- mesmo
        efeito final de segundo_fator_confirmar em webauthn_2fa.py.

        Corpo esperado (JSON): {"codigo": "123456"}.

        Retorno:
            200 com dados de usuário/empresa se o código for válido.
            401 com tentativas_restantes se o código for inválido.
            429 se as tentativas de TOTP desta sessão se esgotarem --
            ALTERADO: isto é agora FIM DA LINHA no login (diferente do
            step-up, ver totp_2fa.py::stepup_totp_confirmar). Não há
            mais fallback para Google sem 2FA (ver oauth.py/login.py/
            mfa.py) -- se WebAuthn já tinha esgotado antes disso (ver
            afterLogin.js), o usuário não tem mais nenhum método
            disponível nesta tentativa de login. O frontend deve
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

        credencial = CredencialTOTP.query.filter_by(
            id_usuario=id_usuario, confirmado=True
        ).first()
        if not credencial:
            return jsonify({"erro": "totp_nao_cadastrado"}), 400

        totp = pyotp.TOTP(credencial.secret_plano)
        if not codigo or not totp.verify(codigo, valid_window=1):
            tentativas += 1
            session["totp_tentativas"] = tentativas
            return jsonify({
                "erro": "codigo_invalido",
                "tentativas_restantes": max(0, MAX_TENTATIVAS_TOTP - tentativas),
            }), 401

        from src.domains.usuario.repository import UsuarioRepository
        from src.domains.auth.services import AuthService
        usuario = UsuarioRepository().find_by_id(id_usuario)

        # ALTERADO: liberação de sessão centralizada em
        # AuthService.liberar_sessao_completa -- mesmo método chamado
        # por webauthn_2fa.py::segundo_fator_confirmar, para não
        # duplicar (e divergir) essa lógica entre os dois módulos.
        AuthService().liberar_sessao_completa(usuario,db)

        return jsonify({
            "id_usuario": usuario.id,
            "email": usuario.email,
            "id_empresa": usuario.id_empresa,
        }), 200

    # ============================================
    # Segundo fator -- STEP-UP (chamado só depois de WebAuthn esgotar
    # tentativas em /stepup/iniciar; NÃO usa sessão mfa_pendente, usa
    # @requer_login normal + vínculo com a ação, igual step_up.py)
    # ============================================

    @staticmethod
    @bp_totp_2fa.post("/2fa/stepup/iniciar")
    @requer_login
    def stepup_totp_iniciar():
        """Confirma TOTP disponível para o step-up da `acao` informada
        e reseta o contador de tentativas específico deste fluxo.

        Corpo esperado (JSON): {"acao": "..."}.

        Retorno:
            200 se o usuário tiver TOTP confirmado.
            400 se `acao` não for informada ou não houver TOTP cadastrado.
        """
        dados = request.get_json(silent=True) or {}
        acao = dados.get("acao")
        if not acao:
            return jsonify({"erro": "acao_nao_especificada"}), 400

        id_usuario = get_id_usuario_sessao()
        credencial = CredencialTOTP.query.filter_by(
            id_usuario=id_usuario, confirmado=True
        ).first()
        if not credencial:
            return jsonify({"erro": "totp_nao_cadastrado"}), 400

        session["stepup_totp_tentativas"] = 0
        session["stepup_totp_acao"] = acao

        return jsonify({
            "metodo": "totp",
            "acao": acao,
            "tentativas_restantes": MAX_TENTATIVAS_TOTP,
        }), 200

    @staticmethod
    @bp_totp_2fa.post("/2fa/stepup/confirmar")
    @requer_login
    def stepup_totp_confirmar():
        """Valida o código TOTP e emite um token de step-up -- mesmo
        formato de stepup_confirmar (WebAuthn) em step_up.py.

        Corpo esperado (JSON): {"acao": "...", "codigo": "123456"}.

        Retorno:
            200 com token_confirmacao se o código for válido.
            401 se a ação não corresponder ao desafio iniciado, ou o
            código for inválido (com tentativas_restantes).
            429 se as tentativas se esgotarem -- ALTERADO: diferente da
            versão anterior deste módulo, isso NÃO é mais fim de linha.
            O frontend deve cair para o fallback senha+Google (mesmo
            fluxo de quando o usuário não tem WebAuthn nem TOTP -- ver
            docstring de step_up.py), não mostrar um estado de bloqueio.
            oferecer nenhum "tentar outro método".
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

        credencial = CredencialTOTP.query.filter_by(
            id_usuario=id_usuario, confirmado=True
        ).first()
        if not credencial:
            return jsonify({"erro": "totp_nao_cadastrado"}), 400

        totp = pyotp.TOTP(credencial.secret_plano)
        if not codigo or not totp.verify(codigo, valid_window=1):
            tentativas += 1
            session["stepup_totp_tentativas"] = tentativas
            return jsonify({
                "erro": "codigo_invalido",
                "tentativas_restantes": max(0, MAX_TENTATIVAS_TOTP - tentativas),
            }), 401

        session.pop("stepup_totp_tentativas", None)
        session.pop("stepup_totp_acao", None)

        # Reaproveita o emissor de token já existente em step_up.py --
        # mesma tabela StepUpToken, mesmo formato para requer_confirmacao_recente.
        from src.domains.auth.step_up import _emitir_token, DURACAO_TOKEN_SEGUNDOS

        token = _emitir_token(id_usuario, acao)

        return jsonify({
            "token_confirmacao": token,
            "acao": acao,
            "expira_em_segundos": DURACAO_TOKEN_SEGUNDOS,
        }), 200
