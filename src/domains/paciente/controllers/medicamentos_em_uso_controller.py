"""
Rotas JSON de medicamentos em uso do paciente (parte do domínio clínico).

Dois blueprints (mesmo padrão da alergia):
- `bp`: LEITURA, em /<uuid_paciente>/medicamentos-em-uso... (só login + tenant).
- `bp_escrita`: ESCRITA, aninhada em um Atendimento:
  /<uuid_atendimento>/pacientes/<uuid_paciente>/medicamentos-em-uso...
  (registrar bp_escrita com url_prefix="/atendimentos").

Auditoria:
- leitura e escritas comuns -> sem log próprio (a tabela já guarda autor/atendimento).
- remover/restaurar -> @acao_sensivel: step-up + LogAlteracao atômico com a
  alteração. Sob @acao_sensivel a view NÃO pode commitar (por isso
  commit=False no service) e precisa devolver (resposta, detalhes).
  O valor de `acao` é o mesmo que o front passa em pedirConfirmacao(acao).

Erros de negócio (BionException): tratados por `_responder_erros_bion`, que
fica POR FORA dos decorators de auditoria. Isso é obrigatório sob
@acao_sensivel: se a view devolvesse json_error() ela mesma, o decorator
não acharia id_registro/uuid_registro e transformaria um 404/409 em erro
500; deixando a exceção subir, ele faz rollback e o tratamento acontece
depois. Em @acesso_auditado, evita logar como "sucesso" uma escrita que
falhou.
"""

from functools import wraps

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_login, requer_papel_clinico,
    get_id_empresa_sessao, get_id_usuario_sessao,
    get_funcao_clinica_sessao,  # <- ajuste se o nome da função de sessão for outro
)
from src.domains.paciente.services import MedicamentoEmUsoService
from src.domains.atendimento.contexto_clinico_service import AutorClinico
from src.domains.auditoria.acaoSensivel import acao_sensivel

bp = Blueprint("medicamentos_em_uso", __name__)
bp_escrita = Blueprint("medicamentos_em_uso_escrita", __name__)
_svc = MedicamentoEmUsoService()

_RECURSO = "medicamentos_em_uso"
_BASE_ESCRITA = "/<uuid_atendimento>/pacientes/<uuid_paciente>/medicamentos-em-uso"


def _responder_erros_bion(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
    return wrapper


def _autor() -> AutorClinico:
    """Quem escreve vem SEMPRE da sessão, nunca do corpo da requisição."""
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


class MedicamentosEmUsoController():

    # ------------------------- LEITURA -------------------------

    @staticmethod
    @bp.get("/<uuid_paciente>/medicamentos-em-uso")
    @_responder_erros_bion
    @requer_login
    def listar_medicamentos_em_uso(uuid_paciente):
        """?ativos=true devolve só os ativos."""
        apenas_ativos = request.args.get("ativos", "").lower() in ("1", "true", "sim")
        itens = _svc.listar_medicamentos_em_uso(
            uuid_paciente, get_id_empresa_sessao(), apenas_ativos=apenas_ativos)
        return json_success(data=[m.to_dict() for m in itens])


    @staticmethod
    @bp.get("/<uuid_paciente>/medicamentos-em-uso/interacoes")
    @_responder_erros_bion
    @requer_login
    def interacoes_do_paciente(uuid_paciente):
        """Cruza os medicamentos ATIVOS do paciente com o catálogo de
        interações. Inclui `nao_verificados` e `cobertura`."""
        resultado = _svc.verificar_interacoes_do_paciente(uuid_paciente, get_id_empresa_sessao())
        return json_success(data=resultado)

    # ------------------------- ESCRITA -------------------------

    @staticmethod
    @bp_escrita.post(_BASE_ESCRITA)
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def registrar_medicamento_em_uso(uuid_atendimento, uuid_paciente):
        dados = request.get_json(silent=True) or {}
        m, alertas = _svc.registrar(uuid_atendimento, uuid_paciente, dados, _autor())
        return json_success(
            data={"medicamento": m.to_dict(), "alertas_interacao": alertas},
            message="Medicamento em uso registrado.", status=201,
        )


    @staticmethod
    @bp_escrita.post(_BASE_ESCRITA + "/<uuid_medicamento>/substituir")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def substituir_medicamento_em_uso(uuid_atendimento, uuid_paciente, uuid_medicamento):
        """Mudança de dose/frequência: fecha o registro atual e cria o novo."""
        dados = request.get_json(silent=True) or {}
        novo = _svc.substituir(uuid_atendimento, uuid_paciente, uuid_medicamento, dados, _autor())
        return json_success(
            data=novo.to_dict(), message="Medicamento em uso substituído.", status=201,
        )


    @staticmethod
    @bp_escrita.post(_BASE_ESCRITA + "/<uuid_medicamento>/encerrar")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def encerrar_medicamento_em_uso(uuid_atendimento, uuid_paciente, uuid_medicamento):
        dados = request.get_json(silent=True) or {}
        m = _svc.encerrar(uuid_atendimento, uuid_paciente, uuid_medicamento, dados, _autor())
        return json_success(
            data=m.to_dict(), message="Medicamento em uso encerrado."
        )

    # ------------------- ESCRITA SENSÍVEL (step-up) -------------------

    @staticmethod
    @bp_escrita.delete(_BASE_ESCRITA + "/<uuid_medicamento>")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("remover_medicamento_em_uso", tabela="medicamentos_em_uso")
    def remover_medicamento_em_uso(uuid_atendimento, uuid_paciente, uuid_medicamento):
        """Soft delete. Motivo no corpo da requisição."""
        dados = request.get_json(silent=True) or {}
        m = _svc.remover(uuid_atendimento, uuid_paciente, uuid_medicamento, dados,
                         _autor(), commit=False)   # o decorator commita (alteração + log)
        justificativa = m.motivo_delete
        if m.observacoes_delete:
            justificativa = f"{m.motivo_delete}: {m.observacoes_delete}"
        return json_success(message="Medicamento em uso removido."), {
            "operacao": "DELETE",
            "id_registro": m.id,
            "uuid_registro": m.uuid,
            "campo_alterado": "deletado",
            "valor_anterior": "false",
            "valor_novo": "true",
            "justificativa": justificativa,
        }


    @staticmethod
    @bp_escrita.post(_BASE_ESCRITA + "/<uuid_medicamento>/restaurar")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("restaurar_medicamento_em_uso", tabela="medicamentos_em_uso")
    def restaurar_medicamento_em_uso(uuid_atendimento, uuid_paciente, uuid_medicamento):
        m = _svc.restaurar(uuid_atendimento, uuid_paciente, uuid_medicamento,
                           _autor(), commit=False)
        return json_success(data=m.to_dict(), message="Medicamento em uso restaurado."), {
            "operacao": "UPDATE",
            "id_registro": m.id,
            "uuid_registro": m.uuid,
            "campo_alterado": "deletado",
            "valor_anterior": "true",
            "valor_novo": "false",
        }