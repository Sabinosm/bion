"""
controller.py

Camada HTTP do domínio Empresa (tenant). Expõe as rotas JSON para consultar e
atualizar a empresa da sessão, cadastrar uma nova empresa junto com o seu
administrador fundador e verificar se um CNPJ/CNES já está em uso. Apenas
traduz requisição e resposta, delegando as regras ao service. Consulta e
atualização dependem do papel do usuário na sessão; cadastro e verificação de
existência são públicos. A atualização é registrada na auditoria como ação
sensível.
"""

from flask import Blueprint, request


from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, get_uuid_empresa_sessao, get_id_empresa_sessao, requer_super_admin
from .service import EmpresaService
from src.domains.auditoria.acaoSensivel import acao_sensivel

bp = Blueprint("empresa", __name__)
_svc = EmpresaService()


class EmpresaController:

    @staticmethod
    @bp.get("/")
    @requer_admin
    def detalhe():
        """Retorna os dados da empresa da sessão."""
        try:
            empresa = _svc.buscar_por_id(get_id_empresa_sessao())
            return json_success(data=empresa.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.put("/")
    @requer_super_admin
    @acao_sensivel(acao="atualizar_empresa", tabela="empresa")
    def atualizar():
        """Atualiza os campos autogerenciáveis da empresa da sessão.

        Body: JSON parcial (campos ausentes não são alterados).
        Em sucesso retorna (resposta, metadados) no formato esperado pelo
        decorator de auditoria. Em erro de negócio retorna só a resposta de
        erro: o decorator vê o status >= 400, desfaz a transação e não audita.
        """
        uuid_empresa = get_uuid_empresa_sessao()
        dados = request.get_json(silent=True) or {}
        try:
            empresa = _svc.atualizar(get_id_empresa_sessao(), dados, uuid_empresa, commit=False)
            resposta = json_success(data=empresa.to_dict(), message="Empresa atualizada.")
            return resposta, {
                "id_registro": empresa.id,
                "uuid_registro": empresa.uuid,
                "operacao": "UPDATE",
            }
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # TODO: definir a ordem de acesso. O ideal seria apresentação dos planos ->
    # pagamento -> criação da empresa; hoje a criação não exige pagamento.
    @staticmethod
    @bp.post("/create")
    def criar():
        """Cadastra a empresa e o admin fundador numa única transação (rota pública).

        Body: {"empresa": {...}, "admin": {...}}
        """
        dados = request.get_json(silent=True) or {}
        dados_empresa = dados.get("empresa", {})
        dados_admin = dados.get("admin", {})

        try:
            empresa, admin = _svc.cadastrar_com_admin(dados_empresa, dados_admin)
            return json_success(
                data={"empresa": empresa.to_dict(), "admin": admin.to_dict()},
                message="Empresa e admin criados com sucesso.",
                status=201,
            )
        except BionException as ex:
            return json_error(ex.message, ex.status_code, erros=ex.erros)

    @staticmethod
    @bp.get("/existe-cnpj/<cnpj>")
    def existe_cnpj(cnpj):
        """Informa se o CNPJ já está cadastrado. Resposta: {"existe": bool}.
        Aceita somente dígitos; qualquer outro caractere é rejeitado."""
        try:
            existe = _svc.cnpj_ja_cadastrado(cnpj)
            return json_success(data={"existe": existe})
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/existe-cnes/<cnes>")
    def existe_cnes(cnes):
        """Informa se o CNES já está cadastrado. Resposta: {"existe": bool}.
        Aceita somente dígitos; qualquer outro caractere é rejeitado."""
        try:
            existe = _svc.cnes_ja_cadastrado(cnes)
            return json_success(data={"existe": existe})
        except BionException as ex:
            return json_error(ex.message, ex.status_code)