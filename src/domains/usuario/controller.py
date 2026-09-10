"""Rotas JSON do dominio Usuario (CRUD administrativo).

ALTERADO (separação admin/papel clínico, assertivo, sem alias):
- @requer_papel("admin") SAIU de todas as rotas (5 ocorrências) --
  substituído por @requer_admin, que checa g.is_admin (sessão) em vez
  de comparar contra um session["tipo_usuario"] que não existe mais.
- atualizar(): g.tipo_usuario != "admin" virou `not g.is_admin`, e
  solicitante_eh_admin=(g.tipo_usuario == "admin") virou
  solicitante_eh_admin=g.is_admin. Um médico-admin passa por essas
  checagens igual a um admin puro -- is_admin nunca depende da função
  clínica.
- atualizar() agora exige STEP-UP (reconfirmação de identidade) quando
  o payload mexe em 'eh_admin' ou 'tipo_papel' -- mesmo tratamento de
  ação sensível que já existia em desativar(). Não dá para decorar a
  rota inteira com @acao_sensivel/@requer_confirmacao_recente, porque
  este MESMO endpoint também edita campos triviais (telefone, email)
  que não deveriam pedir reconfirmação. A checagem é condicional,
  dentro da view, usando `token_recente_valido()` (extraída de
  step_up.py -- mesma função que o decorator usa por baixo, sem
  duplicar a lógica de validação/consumo do token).

ALTERADO (múltiplos admins por empresa, preexistente):
- criar(): quando o payload pede eh_admin=True, a rota exige o
  super admin -- a checagem fina continua sendo feita dentro do
  service (que já bloqueia se solicitante_eh_super_admin=False e
  eh_admin=True). O que muda aqui é repassar g.is_super_admin ao
  service.
- atualizar()/desativar()/ativar(): passam g.is_super_admin adiante,
  necessário para o service decidir se o solicitante pode mexer num
  usuário que já é admin.
"""

from flask import Blueprint, request, g

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
        especialidade = request.args.get('especialidade') # 
        status = request.args.get('status', type=str) # Pendente - Ativo - inativo
        pagina = request.args.get('pagina', default=0, type=int)

        usuarios = _svc.listar(get_id_empresa_sessao(),offset=int(pagina*8),status=status,especialidade=especialidade)
        return json_success(data=[u.to_dict_few() for u in usuarios])



    @staticmethod
    @bp.get("/<uuid>")
    @requer_login
    def detalhe(uuid):
        try:
            u = _svc.buscar_por_uuid(uuid)
            return json_success(data=u.to_dict())
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
        except BionException as e:
            return json_error(e.message, e.status_code)


    @staticmethod
    @bp.put("/<uuid>")
    @requer_login
    def atualizar(uuid):
        # ALTERADO: era g.tipo_usuario != "admin" -- lia o campo errado
        # (tipo_usuario não existe mais na sessão). is_admin é a fonte
        # de verdade correta, e é ortogonal à função clínica: um
        # médico-admin passa por aqui igual a um admin puro.
        if uuid != g.uuid_usuario and not g.is_admin:
            return json_error("Você só pode atualizar o seu próprio cadastro.", 403)

        dados = request.get_json(silent=True) or {}

        # ADICIONADO: step-up condicional. Este mesmo endpoint edita
        # tanto campos triviais (telefone, email) quanto eh_admin/
        # tipo_papel -- só o segundo caso é ação sensível. Diferente de
        # desativar() (rota inteira dedicada, decorável com
        # @acao_sensivel sem ambiguidade), aqui a sensibilidade depende
        # do CONTEÚDO do payload, então a checagem é manual, dentro da
        # view, usando a mesma função que o decorator usa por baixo
        # (token_recente_valido -- ver step_up.py).
        #
        # DECISÃO CONFIRMADA: só a barreira de step-up por enquanto,
        # sem LogAlteracao de auditoria -- att() continua commitando
        # sozinho via repo.save(), sem o contrato (resposta, detalhes)
        # que @acao_sensivel exigiria. Se auditoria completa for
        # necessária depois, revisitar junto de service_atualizar.py.
        mexe_em_campo_sensivel = "eh_admin" in dados or "tipo_papel" in dados
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
                solicitante_eh_admin=g.is_admin,
                solicitante_uuid=g.uuid_usuario,
                solicitante_eh_super_admin=g.is_super_admin,
            )
            return json_success(data=u.to_dict(), message="Usuário atualizado.")
        except BionException as e:
            return json_error(e.message, e.status_code)


    @staticmethod
    @bp.post("/<uuid>/desativar")
    @requer_admin
    @acao_sensivel(acao="desativar_profissional",tabela="Usuarios")
    def desativar(uuid):
        try:
            u = _svc.desativar(uuid, solicitante_eh_super_admin=g.is_super_admin)
            return json_success(data=u.to_dict(), message="Usuário desativado.")
        except BionException as e:
            return json_error(e.message, e.status_code)


    @staticmethod
    @bp.post("/<uuid>/ativar")
    @requer_admin
    @StepUp.requer_confirmacao_recente("desativar_profissional")
    def ativar(uuid):
        try:
            u = _svc.ativar(uuid, solicitante_eh_super_admin=g.is_super_admin)
            if u:
                return json_success(data=u.to_dict(), message="Usuário ativado.")
            else:
                return json_error("Usuário pendente não pode ser ativado manualmente", 422)
        except BionException as e:
            return json_error(e.message, e.status_code)


    # TODO parte do admin ( primeiro to fazendo o 2FA depois eu sigo para essa parte)

    @staticmethod
    @bp.route("/<uuid>/usuarios/<uuid_usuario>/resetar-2fa", methods=["POST"])
    @requer_admin
    def resetar_2fa(uuid_usuario):
        return _svc.reset_2fa(uuid_usuario)
    
    
    @staticmethod
    @bp.route("/<uuid>/usuarios/<uuid_usuario>/resetar-completo", methods=["POST"])
    @requer_admin
    def resetar_completo(uuid_usuario):
        return _svc.reset_total(uuid_usuario)