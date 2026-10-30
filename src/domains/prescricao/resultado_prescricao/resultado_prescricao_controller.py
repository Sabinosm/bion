"""Rotas JSON da entidade ResultadoPrescricao: diagnóstico, desfecho clínico e ciclo do rascunho.

Sem step-up (a prescrição acontece durante o atendimento). Só `confirmar` é auditado (@acesso_auditado, ver ../auditoria_helpers.py);
os demais passos ficam rastreados na própria tabela (formulado_por, origem_sugestao, descartado_*). Só o médico dono escreve; a regra de "atendimento em andamento",
"um rascunho por atendimento" e "alterou -> deixa de ser da IA" mora no service.

  POST   /atendimento/<uuid_atendimento>   cria o rascunho (modo manual)
  GET    /atendimento/<uuid_atendimento>   lista os resultados do atendimento (rascunho/confirmado/descartado)
  GET    /<uuid_resultado>                 detalhe com itens
  GET    /<uuid_resultado>/alertas         interações do conjunto atual
  PATCH  /<uuid_resultado>                 corrige o diagnóstico (origem passa a 'medico')
  POST   /<uuid_resultado>/confirmar       rascunho -> confirmado
  POST   /<uuid_resultado>/descartar       rascunho -> descartado (lógico; motivo opcional)
"""

from flask import Blueprint, request
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao,
)
from src.domains.auditoria.acaoSensivel import acesso_auditado
from .resultado_prescricao_service import ResultadoPrescricaoService
from src.domains.auditoria.auditoria_helpers_service import detalhes, erro
from ..schema_prescricoes import (
    ResultadoPrescricaoIn, ResultadoPrescricaoPatch, ConfirmacaoPrescricaoIn, DescartarPrescricaoIn,
    formatar_erros_pydantic,
)

bp_resultado_prescricao = Blueprint("resultado_prescricao", __name__)
_svc_resultado = ResultadoPrescricaoService()

class ResultadoPrescricaoController():

    @staticmethod
    @bp_resultado_prescricao.post("/atendimento/<uuid_atendimento>")
    @requer_papel_clinico("medico")
    def registrar_resultado(uuid_atendimento):
        """Registra (em rascunho) o diagnóstico (CID-10) e desfecho de um Atendimento em andamento.
        409 se já houver rascunho no atendimento."""
        dados = request.get_json(silent=True) or {}
        try:
            d = ResultadoPrescricaoIn.model_validate(dados)
            r = _svc_resultado.registrar_resultado(
                uuid_atendimento, d, get_id_empresa_sessao(), get_id_usuario_sessao())
            return json_success(data=r.to_dict(), message="Resultado de prescrição registrado (rascunho).",
                                status=201)
        except ValidationError as ex:
            return json_error(formatar_erros_pydantic(ex), 422)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_resultado_prescricao.get("/atendimento/<uuid_atendimento>")
    @requer_papel_clinico("medico")
    def listar_do_atendimento(uuid_atendimento):
        """Resultados do atendimento, do mais antigo ao mais novo, com os itens. Só o médico dono.
        É por aqui que a tela reencontra o rascunho depois de recarregar a página."""
        try:
            itens = _svc_resultado.listar_do_atendimento(
                uuid_atendimento, get_id_empresa_sessao(), get_id_usuario_sessao())
            return json_success(data=[r.to_dict() for r in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_resultado_prescricao.get("/<uuid_resultado>")
    @requer_papel_clinico("medico", "enfermeiro")
    def detalhe_resultado(uuid_resultado):
        """Retorna os detalhes de um ResultadoPrescricao (com itens) pelo UUID, só da própria empresa."""
        try:
            r = _svc_resultado.buscar_resultado_por_uuid(uuid_resultado, get_id_empresa_sessao())
            return json_success(data=r.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_resultado_prescricao.get("/<uuid_resultado>/alertas")
    @requer_papel_clinico("medico")
    def alertas_resultado(uuid_resultado):
        """Alertas de interação do conjunto atual de medicamentos + cobertura da base.
        Lista vazia NÃO significa ausência de interação clínica (ver cobertura.aviso)."""
        try:
            verificacao = _svc_resultado.verificar_alertas(uuid_resultado, get_id_empresa_sessao())
            return json_success(data=verificacao)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_resultado_prescricao.patch("/<uuid_resultado>")
    @requer_papel_clinico("medico")
    def atualizar_resultado(uuid_resultado):
        """Corrige o diagnóstico do rascunho (só os campos enviados). Se algo mudou, a prescrição
        passa a ser do médico (origem_sugestao='medico')."""
        dados = request.get_json(silent=True) or {}
        try:
            patch = ResultadoPrescricaoPatch.model_validate(dados)
            r = _svc_resultado.atualizar_diagnostico(
                uuid_resultado, patch, get_id_empresa_sessao(), get_id_usuario_sessao())
            return json_success(data=r.to_dict(), message="Diagnóstico atualizado.")
        except ValidationError as ex:
            return json_error(formatar_erros_pydantic(ex), 422)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_resultado_prescricao.post("/<uuid_resultado>/confirmar")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="confirmar prescrição", operacao="escrita")
    def confirmar_resultado(uuid_resultado):
        """O médico responsável confirma a prescrição (rascunho -> confirmado).
        Com alertas de interação, exige {"reconhecer_alertas": true}."""
        dados = request.get_json(silent=True) or {}
        try:
            conf = ConfirmacaoPrescricaoIn.model_validate(dados)
            r, verificacao = _svc_resultado.confirmar(
                uuid_resultado, get_id_empresa_sessao(), get_id_usuario_sessao(), conf.reconhecer_alertas
            )
            return (json_success(data={"resultado": r.to_dict(), **verificacao}, message="Prescrição confirmada."),
                    detalhes(r))
        except ValidationError as ex:
            return erro(json_error(formatar_erros_pydantic(ex), 422))
        except BionException as ex:
            return erro(json_error(ex.message, ex.status_code))

    @staticmethod
    @bp_resultado_prescricao.post("/<uuid_resultado>/descartar")
    @requer_papel_clinico("medico")
    def descartar_resultado(uuid_resultado):
        """Descarta o rascunho (lógico: nada é apagado). Corpo opcional: {"motivo": "..."}."""
        dados = request.get_json(silent=True) or {}
        try:
            corpo = DescartarPrescricaoIn.model_validate(dados)
            r = _svc_resultado.descartar(
                uuid_resultado, get_id_empresa_sessao(), get_id_usuario_sessao(), corpo.motivo)
            return json_success(data=r.to_dict(), message="Prescrição descartada.")
        except ValidationError as ex:
            return json_error(formatar_erros_pydantic(ex), 422)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)