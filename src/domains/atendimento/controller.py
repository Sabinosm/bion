"""Rotas JSON do ciclo de vida do Atendimento (abertura, finalização e cancelamento).

Permissões por NÍVEL MÍNIMO (médico ⊃ enfermeiro; ver sessaoPapeis.py):
  - triagem ........... enfermeiro ou médico
  - avaliação médica .. só médico
  - reavaliação ....... só médico (Consulta em em-observacao)
Finalizar e cancelar: só o profissional que abriu o atendimento (o service
devolve 403 para os demais). Finalizar também exige o binário completo.
Toda rota passa o id_empresa da sessão: Atendimento herda a posse da
Consulta, e UUID sozinho não prova posse.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_papel_clinico, get_funcao_clinica_sessao, get_id_usuario_sessao, get_id_empresa_sessao,
)
from src.domains.auditoria.acaoSensivel import acesso_auditado
from .service import AtendimentoService

bp_atendimento = Blueprint("atendimento", __name__)
_svc = AtendimentoService()


class AtendimentoController():

    @staticmethod
    @bp_atendimento.get("/")
    @requer_papel_clinico("enfermeiro", "medico")
    @acesso_auditado(recurso="lista de atendimentos", operacao="leitura")
    def lista_atendimentos():
        """Lista os Atendimentos da empresa do usuário logado."""
        itens = _svc.listar(get_id_empresa_sessao())
        return json_success(data=[a.to_dict() for a in itens])

    @staticmethod
    @bp_atendimento.get("/<uuid>")
    @requer_papel_clinico("enfermeiro", "medico")
    @acesso_auditado(recurso="visualizar atendimento", operacao="leitura")
    def detalhe_atendimento(uuid):
        """Retorna os detalhes de um Atendimento pelo UUID."""
        try:
            a = _svc.buscar_por_uuid(uuid, get_id_empresa_sessao())
            return json_success(data=a.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_atendimento.get("/consulta/<uuid_consulta>")
    @requer_papel_clinico("enfermeiro","medico")
    @acesso_auditado(recurso="atendimentos da consulta", operacao="leitura")
    def atendimentos_da_consulta(uuid_consulta):
        """Lista os Atendimentos vinculados a uma Consulta."""
        try:
            itens = _svc.listar_por_consulta(uuid_consulta, get_id_empresa_sessao())
            return json_success(data=[a.to_dict() for a in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_atendimento.post("/consulta/<uuid_consulta>/abrir-triagem")
    @requer_papel_clinico("enfermeiro", "medico")
    def abrir_triagem(uuid_consulta):
        """Abre um Atendimento do tipo triagem para a Consulta informada.
        409 se o consentimento LGPD estiver pendente ou a Consulta encerrada."""
        try:
            a = _svc.abrir_triagem(uuid_consulta, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Triagem aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_atendimento.post("/consulta/<uuid_consulta>/abrir-avaliacao-medica")
    @requer_papel_clinico("medico")
    def abrir_avaliacao_medica(uuid_consulta):
        """Abre um Atendimento do tipo avaliação médica para a Consulta informada."""
        try:
            a = _svc.abrir_avaliacao_medica(uuid_consulta, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Avaliação médica aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_atendimento.post("/consulta/<uuid_consulta>/abrir-reavaliacao")
    @requer_papel_clinico("medico")
    def abrir_reavaliacao(uuid_consulta):
        """Abre um Atendimento do tipo reavaliação (retorno do médico) para a Consulta informada.
        409 se a Consulta não estiver em em-observacao, houver atendimento em andamento,
        o consentimento estiver pendente ou a Consulta estiver encerrada."""
        try:
            a = _svc.abrir_reavaliacao(uuid_consulta, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=a.to_dict(), message="Reavaliação aberta.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_atendimento.post("/<uuid_atendimento>/finalizar")
    @requer_papel_clinico("enfermeiro", "medico")
    def finalizar_atendimento(uuid_atendimento):
        """Finaliza um Atendimento em andamento. Só o dono (403); exige o
        binário completo (409). Avaliação médica e reavaliação: só médico (403 para enfermeiro)."""
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            dados = {}
        try:
            a = _svc.finalizar(
                uuid_atendimento, get_id_empresa_sessao(), get_id_usuario_sessao(),
                dados.get("observacoes"),
                eh_medico=get_funcao_clinica_sessao() == "medico",
            )
            return json_success(data=a.to_dict(), message="Atendimento finalizado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp_atendimento.post("/<uuid_atendimento>/cancelar")
    @requer_papel_clinico("enfermeiro", "medico")
    def cancelar_atendimento(uuid_atendimento):
        """Cancela um Atendimento em andamento. Só o dono; não exige binário.
        Corpo opcional: {"motivo_cancelamento": "erro-abertura"}."""
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            dados = {}
        try:
            a = _svc.cancelar(
                uuid_atendimento, get_id_empresa_sessao(), get_id_usuario_sessao(),
                dados.get("motivo_cancelamento"),
            )
            return json_success(data=a.to_dict(), message="Atendimento cancelado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)