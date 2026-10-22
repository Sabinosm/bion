"""Rotas da avaliacao Bion. Registre bp_bion no app (ex.: url_prefix="/api").

  POST /atendimento/<uuid_atendimento>/avaliacao-bion  -> 202 {uuid_output, status}
  GET  /avaliacao-bion/<uuid_output>                   -> status e, se concluido, o output_front
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
        409 se não for avaliação médica ou reavaliação em andamento, faltar o input de protocolo ou já houver uma avaliação em curso."""
        try:
            out = servico().iniciar(uuid_atendimento, get_id_empresa_sessao(), get_id_usuario_sessao(),
                                    eh_medico=get_funcao_clinica_sessao() == "medico")
            return json_success(data={"uuid_output": out.uuid, "status": out.status},
                                message="Avaliação iniciada.", status=202)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_bion.get("/avaliacao-bion/<uuid_output>")
    @requer_papel_clinico("medico")
    @acesso_auditado(recurso="avaliação do Bion", operacao="leitura")
    def consultar(uuid_output):
        """Status da avaliação; concluída, traz conduta, perguntas, explicação e qualidade do input."""
        try:
            return json_success(data=servico().consultar(uuid_output, get_id_empresa_sessao(),
                                                         get_id_usuario_sessao()))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
