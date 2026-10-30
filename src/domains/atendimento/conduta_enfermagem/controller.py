"""Rotas JSON da conduta de enfermagem dentro de um Atendimento.

Registrar o blueprint `bp_conduta_enfermagem` sob o MESMO prefixo do `bp_binario`
(o que expõe /<uuid_atendimento>/pacientes/<uuid_paciente>/...).

  POST /<uuid_atendimento>/pacientes/<uuid_paciente>/condutas-enfermagem   registra (insert-only)
  GET  /<uuid_atendimento>/condutas-enfermagem                             condutas do atendimento
  GET  /consulta/<uuid_consulta>/condutas-enfermagem                       condutas da consulta toda

Permissão: enfermeiro ou médico. O resto (dono, em andamento, só triagem, óbito) vem do service.
Sem log de auditoria próprio: a conduta é insert-only e já guarda autor, atendimento e horário.
"""

from flask import Blueprint, request
from pydantic import ValidationError

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.erros_pydantic import erros_pydantic_por_campo
from src.core.session import (
    requer_papel_clinico, get_id_empresa_sessao, get_id_usuario_sessao, get_funcao_clinica_sessao,
)
from src.domains.atendimento.contexto_clinico_service import AutorClinico
from .schema import CondutaEnfermagemCriarSchema
from .service import CondutaEnfermagemService

bp_conduta_enfermagem = Blueprint("conduta_enfermagem", __name__)
_svc = CondutaEnfermagemService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/condutas-enfermagem"


def _autor() -> AutorClinico:
    """Monta o AutorClinico a partir da sessão (nunca do corpo da requisição)."""
    return AutorClinico(
        id_usuario=get_id_usuario_sessao(),
        funcao_clinica=get_funcao_clinica_sessao(),
        id_empresa=get_id_empresa_sessao(),
    )


class CondutaEnfermagemController():

    @staticmethod
    @bp_conduta_enfermagem.post(_ESC)
    @requer_papel_clinico("enfermeiro", "medico")
    def registrar_conduta(uuid_atendimento, uuid_paciente):
        """Registra uma conduta de enfermagem no atendimento de triagem em andamento."""
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            dados = {}
        try:
            corpo = CondutaEnfermagemCriarSchema.model_validate(dados)
        except ValidationError as ex:
            return erros_pydantic_por_campo(ex)
        try:
            c = _svc.registrar(uuid_atendimento, uuid_paciente,
                               corpo.model_dump(exclude_unset=True), _autor())
            return json_success(data=c.to_dict(), message="Conduta de enfermagem registrada.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_conduta_enfermagem.get("/<uuid_atendimento>/condutas-enfermagem")
    @requer_papel_clinico("enfermeiro", "medico")
    def condutas_do_atendimento(uuid_atendimento):
        """Lista as condutas de enfermagem de um Atendimento."""
        try:
            itens = _svc.listar_por_atendimento(uuid_atendimento, get_id_empresa_sessao())
            return json_success(data=[c.to_dict() for c in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_conduta_enfermagem.get("/consulta/<uuid_consulta>/condutas-enfermagem")
    @requer_papel_clinico("enfermeiro", "medico")
    def condutas_da_consulta(uuid_consulta):
        """Lista as condutas de enfermagem de todos os Atendimentos de uma Consulta."""
        try:
            itens = _svc.listar_por_consulta(uuid_consulta, get_id_empresa_sessao())
            return json_success(data=[c.to_dict() for c in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)