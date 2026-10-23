"""controller.py -- rotas JSON do domínio Usuario.

Expõe o CRUD administrativo de usuários (listar, detalhar, criar,
atualizar, ativar, desativar), os resets de credencial feitos pelo
administrador principal (2FA, senha, reset completo), a troca de senha
pelo próprio usuário e o gerenciamento da foto de perfil.

@requer_admin só garante "é admin de alguma empresa"; operações sobre
outros administradores e os resets exigem o super admin (g.is_super_admin),
checado aqui e de novo no service. A atualização exige reconfirmação de
identidade (step-up) apenas quando o payload mexe em is_admin ou
tipo_papel, pois o mesmo endpoint edita campos triviais (telefone, e-mail,
CRM/COREN). A troca de senha pelo próprio usuário também exige step-up.
Todo acesso a um usuário-alvo é restrito à empresa da sessão.

IMPORTANTE -- contrato com @acao_sensivel: toda view decorada precisa
retornar (resposta_flask, detalhes), com ao menos 'id_registro' e
'uuid_registro' em detalhes (ver acaoSensivel.py). Sem isso o decorator
levanta ValueError e faz rollback de QUALQUER alteração pendente na
sessão, mesmo com a resposta HTTP já montada como sucesso. Vale também
para retornos de erro precoce: nesses casos os detalhes vão "vazios"
(id_registro=None, operacao="NOOP"), só para cumprir o contrato.
"""

from flask import Blueprint, request, g
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_admin, get_id_empresa_sessao, get_id_usuario_sessao
from .services.service import UsuarioService
from src.domains.auth.step_up import token_recente_valido
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
            u = _svc.buscar_por_uuid_da_empresa(uuid, get_id_empresa_sessao())
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
                commit=True,
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
                id_empresa_solicitante=get_id_empresa_sessao(),
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
            u = _svc.desativar(
                uuid,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
                commit=False,
            )
            resposta = json_success(data=u.to_dict(), message="Usuário desativado.")
            return resposta, {
                "id_registro": u.id,
                "uuid_registro": u.uuid,
                "operacao": "UPDATE",
                "campo_alterado": "status",
                "valor_novo": "inativo",
            }
        except BionException as e:
            resposta = json_error(e.message, e.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}

    @staticmethod
    @bp.post("/<uuid>/ativar")
    @requer_admin
    @acao_sensivel(acao="ativar_profissional", tabela="Usuarios")
    def ativar(uuid):
        try:
            u = _svc.ativar(
                uuid,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
                commit=False,
            )
            if u:
                resposta = json_success(data=u.to_dict(), message="Usuário ativado.")
                return resposta, {
                    "id_registro": u.id,
                    "uuid_registro": u.uuid,
                    "operacao": "UPDATE",
                    "campo_alterado": "status",
                    "valor_novo": "ativo",
                }
            else:
                resposta = json_error("Usuário pendente não pode ser ativado manualmente", 422)
                return resposta, {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}
        except BionException as e:
            resposta = json_error(e.message, e.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}

    @staticmethod
    @bp.post("/<uuid_usuario>/resetar-2fa")
    @requer_admin
    @acao_sensivel(acao="resetar_2fa_usuario", tabela="Usuarios")
    def resetar_2fa(uuid_usuario):
        if not g.is_super_admin:
            resposta = json_error(
                "Apenas o administrador principal pode resetar o 2FA de um usuário.",
                403,
            )
            return resposta, {"id_registro": None, "uuid_registro": uuid_usuario, "operacao": "NOOP"}
        try:
            u = _svc.reset_2fa(
                uuid_usuario,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
                commit=False,
            )
            resposta = json_success(
                data=u.to_dict(),
                message="2FA resetado. O usuário precisará cadastrar um novo dispositivo.",
            )
            return resposta, {
                "id_registro": u.id,
                "uuid_registro": u.uuid,
                "operacao": "DELETE",
                "campo_alterado": "credenciais_2fa",
                "justificativa": "Reset de 2FA solicitado pelo administrador principal.",
            }
        except BionException as e:
            resposta = json_error(e.message, e.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid_usuario, "operacao": "NOOP"}

    @staticmethod
    @bp.post("/<uuid_usuario>/resetar-completo")
    @requer_admin
    @acao_sensivel(acao="resetar_completo_usuario", tabela="Usuarios")
    def resetar_completo(uuid_usuario):
        if not g.is_super_admin:
            resposta = json_error(
                "Apenas o administrador principal pode resetar um usuário por completo.",
                403,
            )
            return resposta, {"id_registro": None, "uuid_registro": uuid_usuario, "operacao": "NOOP"}
        try:
            u = _svc.reset_total(
                uuid_usuario,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
                commit=False,
            )
            resposta = json_success(
                data=u.to_dict(),
                message="Usuário resetado por completo. Ele precisará refazer a ativação de conta.",
            )
            return resposta, {
                "id_registro": u.id,
                "uuid_registro": u.uuid,
                "operacao": "DELETE",
                "campo_alterado": "credenciais_2fa,hash_senha,status",
                "justificativa": "Reset completo solicitado pelo administrador principal.",
            }
        except BionException as e:
            resposta = json_error(e.message, e.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid_usuario, "operacao": "NOOP"}

    @staticmethod
    @bp.put("/senha")
    @requer_login
    @acao_sensivel(acao="alterar_senha", tabela="Usuarios")
    def alterar_senha():
        if not token_recente_valido("alterar_senha"):
            resposta = json_error(
                "Confirmação de identidade necessária para alterar a senha.",
                403,
            )
            return resposta, {"id_registro": None, "uuid_registro": g.uuid_usuario, "operacao": "NOOP"}

        dados = request.get_json(silent=True) or {}
        try:
            u = _svc.alterar_senha(g.uuid_usuario, dados, commit=False)
            resposta = json_success(
                message="Senha alterada. Você precisará entrar novamente em outros dispositivos."
            )
            return resposta, {
                "id_registro": u.id,
                "uuid_registro": u.uuid,
                "operacao": "UPDATE",
                "campo_alterado": "hash_senha",
            }
        except BionException as e:
            resposta = json_error(e.message, e.status_code)
            return resposta, {"id_registro": None, "uuid_registro": g.uuid_usuario, "operacao": "NOOP"}

    @staticmethod
    @bp.post("/<uuid_usuario>/resetar-senha")
    @requer_admin
    @acao_sensivel(acao="resetar_senha_usuario", tabela="Usuarios")
    def resetar_senha(uuid_usuario):
        # Só a senha muda (2FA e status ficam intactos) e nenhuma senha
        # temporária é devolvida: o usuário define a nova no onboarding.
        if not g.is_super_admin:
            resposta = json_error(
                "Apenas o administrador principal pode resetar a senha de um usuário.",
                403,
            )
            return resposta, {"id_registro": None, "uuid_registro": uuid_usuario, "operacao": "NOOP"}
        try:
            u = _svc.resetar_senha_usuario(
                uuid_usuario,
                id_empresa_solicitante=get_id_empresa_sessao(),
                solicitante_eh_super_admin=g.is_super_admin,
                commit=False,
            )
            resposta = json_success(
                data=u.to_dict(),
                message="Senha resetada. O usuário precisará definir uma nova senha "
                        "no próximo login.",
            )
            return resposta, {
                "id_registro": u.id,
                "uuid_registro": u.uuid,
                "operacao": "UPDATE",
                "campo_alterado": "hash_senha",
                "justificativa": "Reset de senha solicitado pelo administrador principal.",
            }
        except BionException as e:
            resposta = json_error(e.message, e.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid_usuario, "operacao": "NOOP"}

    @staticmethod
    @bp.get("/avatar")
    @requer_login
    def verificar_avatar():
        # Rota estática: o Flask a prioriza sobre GET /<uuid>, então não
        # há conflito com o detalhe de usuário.
        try:
            info = _svc.verificar_avatar_usuario(get_id_usuario_sessao())
            return json_success(data=info)
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.delete("/avatar")
    @requer_login
    def remover_avatar():
        try:
            usuario = _svc.remover_avatar_usuario(get_id_usuario_sessao())
            if not usuario:
                return json_error("Nenhuma imagem encontrada para ser deletada.", 404)
            return json_success(data=usuario.to_dict(), message="Avatar removido com sucesso.")
        except BionException as e:
            return json_error(e.message, e.status_code)

    @staticmethod
    @bp.post("/avatar")
    @requer_login
    def atualizar_avatar():
        if 'file' not in request.files or request.files['file'].filename == '':
            return json_error("Nenhum arquivo foi selecionado.", 400)
            
        file = request.files['file']
        try:
            usuario = _svc.atualizar_avatar_usuario(get_id_usuario_sessao(), file=file)
            return json_success(data=usuario.to_dict(), message="Avatar atualizado com sucesso.")
        except BionException as e:
            return json_error(e.message, e.status_code)