"""Rotas JSON da entidade Prescricao: medicamentos prescritos.

Sem step-up; auditoria por @acesso_auditado (ver auditoria_helpers.py). Todas só para o médico dono,
com o atendimento em andamento e a prescrição em rascunho (regras no service)."""

from flask import Blueprint, request
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao
from src.domains.auditoria.acaoSensivel import acesso_auditado
from src.domains.auditoria.auditoria_helpers_service import detalhes, erro
from .prescricao_service import PrescricaoService
from .schema_prescricoes import MedicamentoPrescritoIn, MedicamentoPrescritoPatch, formatar_erros_pydantic

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
        dados = request.get_json(silent=True) or {}
        try:
            item = MedicamentoPrescritoIn.model_validate(dados)
            p, verificacao = _svc_prescricao.adicionar_medicamento(
                uuid_resultado, item, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return (json_success(
                data={"prescricao": p.to_dict(), **verificacao},
                message="Medicamento prescrito.", status=201,
            ), detalhes(p.resultado_prescricao))
        except ValidationError as ex:
            return erro(json_error(formatar_erros_pydantic(ex), 422))
        except BionException as ex:
            return erro(json_error(ex.message, ex.status_code))

    @staticmethod
    @bp_prescricao.patch("/<uuid_resultado>/medicamentos/<uuid_item>")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="alterar medicamento da prescrição", operacao="escrita")
    def atualizar_medicamento(uuid_resultado, uuid_item):
        """Altera dose, frequência, duração ou orientações (só o que foi enviado). Se algo mudou, o
        item e a prescrição passam a ser do médico."""
        dados = request.get_json(silent=True) or {}
        try:
            patch = MedicamentoPrescritoPatch.model_validate(dados)
            p = _svc_prescricao.atualizar_medicamento(
                uuid_resultado, uuid_item, patch, get_id_empresa_sessao(), get_id_usuario_sessao()
            )
            return (json_success(data=p.to_dict(), message="Medicamento atualizado."),
                    detalhes(p.resultado_prescricao))
        except ValidationError as ex:
            return erro(json_error(formatar_erros_pydantic(ex), 422))
        except BionException as ex:
            return erro(json_error(ex.message, ex.status_code))

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
            return erro(json_error(ex.message, ex.status_code))