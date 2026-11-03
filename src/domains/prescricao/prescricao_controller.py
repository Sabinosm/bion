"""prescricao_controller.py

Rotas JSON dos medicamentos prescritos: adicionar, alterar e remover um
medicamento do rascunho de prescrição. Só o médico dono, com o atendimento em
andamento e a prescrição em rascunho (as regras vivem no service).

Sem step-up: a prescrição acontece durante o atendimento. A auditoria é por
acesso auditado, e toda resposta de erro devolve a meta NOOP (ver
prescricao_controller_helpers.py).
"""

from flask import Blueprint
from pydantic import ValidationError

from src.core.exceptions import BionException
from src.core.responses import json_success
from src.core.session import requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao
from src.domains.auditoria.acaoSensivel import acesso_auditado
from src.domains.auditoria.auditoria_helpers_service import detalhes
from .prescricao_controller_helpers import corpo_json, erro_bion, erro_validacao
from .prescricao_service import PrescricaoService
from .schema_prescricoes import MedicamentoPrescritoIn, MedicamentoPrescritoPatch

bp_prescricao = Blueprint("prescricao", __name__)
_svc_prescricao = PrescricaoService()


class PrescricaoController():

    @staticmethod
    @bp_prescricao.post("/<uuid_resultado>/medicamentos")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="adicionar medicamento à prescrição", operacao="escrita")
    def adicionar_medicamento(uuid_resultado):
        """Adiciona um medicamento (por uuid_catalogo) ao rascunho do médico; o resultado passa a ser
        do médico. A resposta traz os alertas de interação do conjunto atual do rascunho."""
        try:
            item = MedicamentoPrescritoIn.model_validate(corpo_json())
            p, verificacao = _svc_prescricao.adicionar_medicamento(
                uuid_resultado, item, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return (json_success(
                data={"prescricao": p.to_dict(), **verificacao},
                message="Medicamento prescrito.", status=201,
            ), detalhes(p.resultado_prescricao))
        except ValidationError as ex:
            return erro_validacao(ex)
        except BionException as ex:
            return erro_bion(ex)

    @staticmethod
    @bp_prescricao.patch("/<uuid_resultado>/medicamentos/<uuid_item>")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="alterar medicamento da prescrição", operacao="escrita")
    def atualizar_medicamento(uuid_resultado, uuid_item):
        """Altera dose, frequência, duração ou orientações (só o que foi enviado). Se algo mudou, o
        item e a prescrição passam a ser do médico."""
        try:
            patch = MedicamentoPrescritoPatch.model_validate(corpo_json())
            p = _svc_prescricao.atualizar_medicamento(
                uuid_resultado, uuid_item, patch, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return (json_success(data=p.to_dict(), message="Medicamento atualizado."),
                    detalhes(p.resultado_prescricao))
        except ValidationError as ex:
            return erro_validacao(ex)
        except BionException as ex:
            return erro_bion(ex)

    @staticmethod
    @bp_prescricao.delete("/<uuid_resultado>/medicamentos/<uuid_item>")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="remover medicamento da prescrição", operacao="escrita")
    def remover_medicamento(uuid_resultado, uuid_item):
        """Remove um medicamento do rascunho (inclusive sugestões da IA que o médico descartou)."""
        try:
            _svc_prescricao.remover_medicamento(
                uuid_resultado, uuid_item, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return json_success(message="Medicamento removido da prescrição."), {}
        except BionException as ex:
            return erro_bion(ex)
