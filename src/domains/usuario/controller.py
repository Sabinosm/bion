"""Rotas JSON do dominio Usuario (CRUD administrativo).

@requer_admin protege as rotas administrativas checando g.is_admin. Em
atualizar(), a exigencia de reconfirmacao de identidade (step-up) e
condicional ao conteudo do payload: so dispara quando o usuario tenta
alterar is_admin ou tipo_papel, ja que o mesmo endpoint tambem edita
campos triviais (telefone, email) que nao devem pedir reconfirmacao.
criar()/atualizar()/desativar()/ativar() repassam g.is_super_admin ao
service, que decide se o solicitante pode mexer num usuario que ja e
admin.
"""

from flask import Blueprint, request, g
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_admin, get_id_empresa_sessao
from .services.service import UsuarioService
from src.domains.auth.step_up import StepUp, token_recente_valido
from src.domains.auditoria.acaoSensivel import acao_sensivel

bp = Blueprint("usuario", __name__)
_svc = UsuarioService()


class UsuarioController():

    @staticmethod
    @bp.get("/")
    @requer_admin
    def lista():
        especialidade = request.args.get('especialidade')
        status = request.args.get('status', type=str)  # pendente - ativo - inativo
        pagina = request.args.get('pagina', default=0, type=int)

        usuarios = _svc.listar(get_id_empresa_sessao(), offset=int(pagina * 8), status=status, especialidade=especialidade)
        return json_success(data=[u.to_dict_few() for u in usuarios])

    @staticmethod
    @bp.get("/<uuid>")
    @requer_admin
    def detalhe(uuid):
        try:
            u = _svc.buscar_por_uuid(uuid)
            return json_success(data=u.to_dict(True))
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.post("/")
    @requer_admin
    def criar():
        dados = request.get_json(silent=True) or {}
        try:
            u = _svc.criar(
                id_empresa=get_id_empresa_sessao(),
                dados=dados,
                commitar=True,
                solicitante_eh_super_admin=g.is_super_admin,
            )
            return json_success(data=u.to_dict(), message="Usuário criado com sucesso.", status=201)
        except ValidationError as e:
            return json_error(str(e), 422)
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.put("/<uuid>")
    @requer_admin
    def atualizar(uuid):
        if uuid != g.uuid_usuario and not g.is_admin:
            return json_error("Você só pode atualizar o seu próprio cadastro.", 403)

        dados = request.get_json(silent=True) or {}

        # Step-up condicional: só exige reconfirmação de identidade quando
        # o payload mexe em campos sensíveis (is_admin, tipo_papel). Usa a
        # mesma função de validação do decorator (token_recente_valido),
        # sem duplicar a lógica, pois aqui a checagem depende do conteúdo
        # do payload e não pode ser resolvida com um decorator estático.
        mexe_em_campo_sensivel = "is_admin" in dados or "tipo_papel" in dados
        if mexe_em_campo_sensivel and not token_recente_valido("alterar_papel_usuario"):
            return json_error(
                "Confirmação de identidade necessária para alterar "
                "administrador ou função clínica.",
                403,
            )

        try:
            u = _svc.atualizar(
                uuid,
                dados,
                solicitante_is_admin=g.is_admin,
                solicitante_uuid=g.uuid_usuario,
                solicitante_eh_super_admin=g.is_super_admin,
            )
            return json_success(data=u.to_dict(), message="Usuário atualizado.")
        except ValidationError as e:
            return json_error(str(e), 422)
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.post("/<uuid>/desativar")
    @requer_admin
    @acao_sensivel(acao="desativar_profissional", tabela="Usuarios")
    def desativar(uuid):
        try:
            u = _svc.desativar(uuid, solicitante_eh_super_admin=g.is_super_admin)
            return json_success(data=u.to_dict(), message="Usuário desativado.")
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.post("/<uuid>/ativar")
    @requer_admin
    @StepUp.requer_confirmacao_recente("ativar_profissional")
    def ativar(uuid):
        try:
            u = _svc.ativar(uuid, solicitante_eh_super_admin=g.is_super_admin)
            if u:
                return json_success(data=u.to_dict(), message="Usuário ativado.")
            else:
                return json_error("Usuário pendente não pode ser ativado manualmente", 422)
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.post("/<uuid_usuario>/resetar-2fa")
    @requer_admin
    @acao_sensivel(acao="resetar_2fa_usuario", tabela="Usuarios")
    def resetar_2fa(uuid_usuario):
        # @requer_admin garante só "é admin de alguma empresa"; resetar
        # 2FA de terceiros exige especificamente o super admin.
        if not g.is_super_admin:
            return json_error(
                "Apenas o administrador principal pode resetar o 2FA de um usuário.",
                403,
            )
        try:
            u = _svc.reset_2fa(
                uuid_usuario,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
            )
            return json_success(
                data=u.to_dict(),
                message="2FA resetado. O usuário precisará cadastrar um novo dispositivo.",
            )
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.post("/<uuid_usuario>/resetar-completo")
    @requer_admin
    @acao_sensivel(acao="resetar_completo_usuario", tabela="Usuarios")
    def resetar_completo(uuid_usuario):
        if not g.is_super_admin:
            return json_error(
                "Apenas o administrador principal pode resetar um usuário por completo.",
                403,
            )
        try:
            u = _svc.reset_total(
                uuid_usuario,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
            )
            return json_success(
                data=u.to_dict(),
                message="Usuário resetado por completo. Ele precisará refazer a ativação de conta.",
            )
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.put("/senha")
    @requer_login
    @StepUp.requer_confirmacao_recente("alterar_senha")
    def alterar_senha():
        dados = request.get_json(silent=True) or {}
        try:
            _svc.alterar_senha(g.uuid_usuario, dados)
            return json_success(
                message="Senha alterada. Você precisará entrar novamente em outros dispositivos."
            )
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.post("/<uuid_usuario>/resetar-senha")
    @requer_admin
    @StepUp.requer_confirmacao_recente("resetar_senha_usuario")
    @acao_sensivel(acao="resetar_senha_usuario", tabela="Usuarios")
    def resetar_senha(uuid_usuario):
        # Reset isolado de senha (diferente de resetar_completo: aqui só
        # a senha muda, WebAuthn e status permanecem intactos). Sem senha
        # temporária no retorno: o usuário define a própria no próximo
        # login, caindo no fluxo de onboarding já existente.
        if not g.is_super_admin:
            return json_error(
                "Apenas o administrador principal pode resetar a senha de um usuário.",
                403,
            )
        try:
            u = _svc.resetar_senha_usuario(
                uuid_usuario,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
            )
            return json_success(
                data=u.to_dict(),
                message="Senha resetada. O usuário precisará definir uma nova senha "
                        "no próximo login.",
            )
        except BionException as e:
            return json_error(e.message, e.status_code)