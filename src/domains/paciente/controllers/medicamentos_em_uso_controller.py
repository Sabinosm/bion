"""medicamentos_em_uso_controller.py

Rotas JSON dos medicamentos em uso do paciente (parte do domínio clínico). Dois
blueprints, no mesmo padrão da alergia:

- `bp`: LEITURA, em /<uuid_paciente>/medicamentos-em-uso..., de médico ou enfermeiro
  da empresa.
- `bp_escrita`: ESCRITA, aninhada em um Atendimento:
  /<uuid_atendimento>/pacientes/<uuid_paciente>/medicamentos-em-uso...
  (registrar `bp_escrita` com url_prefix="/atendimentos").

Auditoria: leitura e escritas comuns não têm log próprio (a tabela já guarda autor e
atendimento). Remover e restaurar são ações sensíveis (step-up + log de alteração atômico
com a alteração). Sob a ação sensível a view NÃO pode comitar (por isso commit=False no
service) e precisa devolver (resposta, detalhes). O valor de `acao` é o mesmo que o front
passa em pedirConfirmacao(acao).

Erros de negócio (BionException) são tratados por `_responder_erros_bion`, que fica POR
FORA dos decorators de auditoria. Isso é obrigatório sob a ação sensível: se a view
devolvesse o erro ela mesma, o decorator não acharia id_registro e uuid_registro e
trataria como falha; deixando a exceção subir, ele desfaz a transação e o tratamento
acontece depois, com a mesma resposta (mensagem, status e `erros` por campo).
"""

from functools import wraps

from flask import Blueprint, request

from src.core.exceptions import BionException
from src.core.responses import json_success
from src.core.session import requer_papel_clinico, get_id_empresa_sessao
from src.domains.auditoria.acaoSensivel import acao_sensivel
from src.domains.paciente.services import MedicamentoEmUsoService
from .comum import autor_clinico, corpo_json, resposta_erro

bp = Blueprint("medicamentos_em_uso", __name__)
bp_escrita = Blueprint("medicamentos_em_uso_escrita", __name__)
_svc = MedicamentoEmUsoService()

_BASE_ESCRITA = "/<uuid_atendimento>/pacientes/<uuid_paciente>/medicamentos-em-uso"


def _responder_erros_bion(f):
    """Converte BionException em resposta de erro (ver o docstring do módulo)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except BionException as ex:
            return resposta_erro(ex)
    return wrapper


class MedicamentosEmUsoController():

    # ------------------------- LEITURA -------------------------

    @staticmethod
    @bp.get("/<uuid_paciente>/medicamentos-em-uso")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def listar_medicamentos_em_uso(uuid_paciente):
        """Medicamentos não removidos do paciente. ?ativos=true devolve só os ativos."""
        apenas_ativos = request.args.get("ativos", "").lower() in ("1", "true", "sim")
        itens = _svc.listar_medicamentos_em_uso(
            uuid_paciente, get_id_empresa_sessao(), apenas_ativos=apenas_ativos)
        return json_success(data=[m.to_dict() for m in itens])

    @staticmethod
    @bp.get("/<uuid_paciente>/medicamentos-em-uso/interacoes")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def interacoes_do_paciente(uuid_paciente):
        """Cruza os medicamentos ATIVOS do paciente com o catálogo de interações. Inclui
        `nao_verificados` e `cobertura`."""
        resultado = _svc.verificar_interacoes_do_paciente(uuid_paciente, get_id_empresa_sessao())
        return json_success(data=resultado)

    # ------------------------- ESCRITA -------------------------

    @staticmethod
    @bp_escrita.post(_BASE_ESCRITA)
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def registrar_medicamento_em_uso(uuid_atendimento, uuid_paciente):
        """Registra um medicamento ativo e devolve os alertas de interação já com o novo item."""
        m, alertas = _svc.registrar(uuid_atendimento, uuid_paciente, corpo_json(), autor_clinico())
        return json_success(
            data={"medicamento": m.to_dict(), "alertas_interacao": alertas},
            message="Medicamento em uso registrado.", status=201,
        )

    @staticmethod
    @bp_escrita.post(_BASE_ESCRITA + "/<uuid_medicamento>/substituir")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def substituir_medicamento_em_uso(uuid_atendimento, uuid_paciente, uuid_medicamento):
        """Mudança de dose ou frequência: fecha o registro atual e cria o novo."""
        novo = _svc.substituir(uuid_atendimento, uuid_paciente, uuid_medicamento,
                               corpo_json(), autor_clinico())
        return json_success(data=novo.to_dict(), message="Medicamento em uso substituído.", status=201)

    @staticmethod
    @bp_escrita.post(_BASE_ESCRITA + "/<uuid_medicamento>/encerrar")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    def encerrar_medicamento_em_uso(uuid_atendimento, uuid_paciente, uuid_medicamento):
        """Fecha o tratamento como 'interrompido' ou 'concluido'."""
        m = _svc.encerrar(uuid_atendimento, uuid_paciente, uuid_medicamento,
                          corpo_json(), autor_clinico())
        return json_success(data=m.to_dict(), message="Medicamento em uso encerrado.")

    # ------------------- ESCRITA SENSÍVEL (step-up) -------------------

    @staticmethod
    @bp_escrita.delete(_BASE_ESCRITA + "/<uuid_medicamento>")
    @_responder_erros_bion
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel("remover_medicamento_em_uso", tabela="medicamentos_em_uso")
    def remover_medicamento_em_uso(uuid_atendimento, uuid_paciente, uuid_medicamento):
        """Soft delete. Motivo no corpo da requisição."""
        m = _svc.remover(uuid_atendimento, uuid_paciente, uuid_medicamento, corpo_json(),
                         autor_clinico(), commit=False)   # o decorator comita (alteração + log)
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
        """Reverte o soft delete."""
        m = _svc.restaurar(uuid_atendimento, uuid_paciente, uuid_medicamento,
                           autor_clinico(), commit=False)
        return json_success(data=m.to_dict(), message="Medicamento em uso restaurado."), {
            "operacao": "UPDATE",
            "id_registro": m.id,
            "uuid_registro": m.uuid,
            "campo_alterado": "deletado",
            "valor_anterior": "true",
            "valor_novo": "false",
        }
