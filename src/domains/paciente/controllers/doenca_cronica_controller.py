"""
Rotas JSON de doenças crônicas do paciente (parte do domínio clínico).

CORRIGIDO: `remover_doenca` chamava `_svc.remover_doenca(...,
commmit=False)` com "commmit" (3 M's) -- a assinatura real do service
é `commit` (2 M's, default True). Isso não era um bug silencioso: toda
chamada levantava TypeError (kwarg inesperado), então esta rota nunca
funcionou. Corrigido para `commit=False`.

ATUALIZADO: `remover_doenca` agora cumpre o contrato de
`acao_sensivel` -- devolve (resposta, detalhes) com id_registro/
uuid_registro/justificativa. Como o service devolve o resultado de
`repo.soft_delete(...)` (não a instância da doença), uuid_doenca -- já
validado dentro do service -- é usado como identificador.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico, get_id_empresa_sessao
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado
from src.domains.paciente.services import DoencaCronicaService

bp = Blueprint("doencas-cronicas", __name__)
_svc = DoencaCronicaService()



class DoencaCronicaController():

    @staticmethod
    @bp.get("/<uuid_paciente>/doencas-cronicas")
    @requer_login
    def listar_doencas(uuid_paciente):
        try:
            itens = _svc.listar_doencas(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[d.to_dict() for d in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/doencas-cronicas")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="adicionar doenca cronica", operacao="escrita")
    def adicionar_doenca(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.adicionar_doenca(uuid_paciente, dados, get_id_empresa_sessao())
            return json_success(data=d.to_dict(), message="Doença crônica registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: corrige/atualiza uma doença crônica já registrada.
    @staticmethod
    @bp.put("/<uuid_paciente>/doencas-cronicas/<uuid_doenca>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="atualizar doenca cronica", operacao="escrita")
    def atualizar_doenca(uuid_paciente, uuid_doenca):
        dados = request.get_json(silent=True) or {}
        try:
            d = _svc.atualizar_doenca(uuid_paciente, uuid_doenca, dados, get_id_empresa_sessao())
            return json_success(data=d.to_dict(), message="Doença crônica atualizada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # NOVO: soft delete -- remove uma doença crônica já registrada.
    # Motivo vem no corpo da requisição (DELETE com body é incomum mas
    # válido em HTTP/REST; alternativa seria query string, mas body
    # mantém consistência com os outros schemas Pydantic do domínio).
    @staticmethod
    @bp.delete("/<uuid_paciente>/doencas-cronicas/<uuid_doenca>")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel(acao="remover_doenca_cronica", tabela="doenca_cronica")
    def remover_doenca(uuid_paciente, uuid_doenca):
        # NOTA: ainda não confirmei o valor de retorno de
        # DoencaCronicaService.remover_doenca -- dado que os services
        # irmãos (AlergiaService.remover_alergia,
        # ObservacaoTipoSanguineoService.remover_tipo_sanguineo) devolvem
        # um bool/resultado de repo, não a instância, assumo o mesmo
        # aqui por cautela e uso uuid_doenca (já validado dentro do
        # service) como identificador. Ajustar se o service devolver a
        # instância de verdade.
        dados = request.get_json(silent=True) or {}
        try:
            # Corrigido: era "commmit" (3 M's), typo que não corresponde
            # a nenhum parâmetro de DoencaCronicaService.remover_doenca
            # (assinatura real usa "commit", 2 M's) -- a chamada
            # levantava TypeError em toda tentativa de remoção.
            _svc.remover_doenca(uuid_paciente, uuid_doenca, dados, get_id_empresa_sessao(), commit=False)
            resposta = json_success(message="Doença crônica removida.")
            return resposta, {
                "id_registro": uuid_doenca,
                "uuid_registro": uuid_doenca,
                "operacao": "DELETE",
                "campo_alterado": "deletado",
                "valor_novo": "True",
                "justificativa": dados.get("motivo_delete") or dados.get("observacoes_delete"),
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid_doenca, "operacao": "NOOP"}

    # NOVO: reverte um soft delete. POST (não PUT) porque é uma ação,
    # não uma substituição de estado do recurso via corpo -- não tem
    # payload, só o efeito colateral de reverter deletado/deletado_em/
    # motivo_delete/observacoes_delete.
    @staticmethod
    @bp.post("/<uuid_paciente>/doencas-cronicas/<uuid_doenca>/restaurar")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="restaurar doenca cronica", operacao="exclusao-logica")
    def restaurar_doenca(uuid_paciente, uuid_doenca):
        try:
            d = _svc.restaurar_doenca(uuid_paciente, uuid_doenca, get_id_empresa_sessao())
            return json_success(data=d.to_dict(), message="Doença crônica restaurada.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)