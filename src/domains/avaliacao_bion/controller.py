"""Rotas da avaliacao Bion. bp_bion é registrado em /v1/api/bion (main.py).

  POST /atendimento/<uuid_atendimento>/avaliacao-bion  -> 202 {uuid_output, status}
  GET  /avaliacao-bion/<uuid_output>/status            -> so o estado (polling; sem conteudo clinico, sem auditoria)
  GET  /atendimento/<uuid_atendimento>/avaliacao-bion/ultima
                                                       -> estado da avaliacao mais recente (ou data null)
  GET  /avaliacao-bion/<uuid_output>                   -> status e, se concluido, o output_front (leitura AUDITADA)

Fluxo do front: POST -> consulta /status ate concluir -> um unico GET completo (1 linha de auditoria).
"""
from flask import Blueprint

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico, get_funcao_clinica_sessao, get_id_usuario_sessao, get_id_empresa_sessao,
)
from src.domains.auditoria.acaoSensivel import acesso_auditado

from .helpers import dependencias
from .service import AvaliacaoBionService

bp_bion = Blueprint("avaliacao_bion", __name__)


@bp_bion.after_request
def _sem_cache(resposta):
    """Dado clinico (e o estado dele) nao pode ficar em cache de navegador ou proxy."""
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


_svc: AvaliacaoBionService | None = None


def servico() -> AvaliacaoBionService:
    """Instancia na primeira chamada (precisa do app e, depois, do cliente de IA real)."""
    global _svc
    if _svc is None:
        _svc = AvaliacaoBionService(dependencias.padrao())
    return _svc


class AvaliacaoBionController:

    @staticmethod
    @bp_bion.post("/atendimento/<uuid_atendimento>/avaliacao-bion")
    @requer_papel_clinico("medico")
    def iniciar(uuid_atendimento):
        """Inicia a avaliação do Bion (assíncrona). 403 se não for o médico do atendimento;
        409 se não for avaliação médica em andamento ou já houver uma avaliação em curso."""
        try:
            out = servico().iniciar(uuid_atendimento, get_id_empresa_sessao(), get_id_usuario_sessao(),
                                    eh_medico=get_funcao_clinica_sessao() == "medico")
            return json_success(data={"uuid_output": out.uuid, "status": out.status},
                                message="Avaliação iniciada.", status=202)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_bion.get("/avaliacao-bion/<uuid_output>/status")
    @requer_papel_clinico("medico")
    def status(uuid_output):
        """Estado para o polling: {uuid_output, status, erro_codigo, criado_em}. Sem conteudo clinico,
        por isso sem @acesso_auditado (o conteudo so sai em consultar, que e auditado)."""
        try:
            return json_success(data=servico().status(uuid_output, get_id_empresa_sessao(),
                                                      get_id_usuario_sessao()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_bion.get("/atendimento/<uuid_atendimento>/avaliacao-bion/ultima")
    @requer_papel_clinico("medico")
    def ultima(uuid_atendimento):
        """Estado da avaliacao mais recente do atendimento; data=null se nunca houve. 403 se nao for o
        profissional do atendimento. Sem conteudo clinico (o front le o conteudo por consultar)."""
        try:
            return json_success(data=servico().ultima(uuid_atendimento, get_id_empresa_sessao(),
                                                      get_id_usuario_sessao()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_bion.get("/avaliacao-bion/<uuid_output>")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="avaliação do Bion", operacao="leitura")
    def consultar(uuid_output):
        """Status da avaliação; concluída, traz conduta, perguntas, explicação e qualidade do input.
        Erro devolve NOOP: o decorator não olha o status HTTP e, sem isso, um 403/404 seria
        registrado no log de acesso como leitura com sucesso."""
        try:
            return json_success(data=servico().consultar(uuid_output, get_id_empresa_sessao(),
                                                         get_id_usuario_sessao())), {}
        except BionException as ex:
            return json_error(ex.message, ex.status_code), {"operacao": "NOOP"}