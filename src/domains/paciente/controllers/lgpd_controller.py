"""
Rotas JSON de consentimento LGPD do paciente. Registrado sob
/v1/api/pacientes/lgpd -- prefixo PRÓPRIO, nem /pessoal nem /clinico.

Decisão confirmada: consentimento diz respeito ao paciente, mas o
PROCESSO (termos, canal de coleta, histórico, revogação) não é pessoal
nem clínico -- é titularidade/LGPD, domínio à parte. Só o RESULTADO
(booleano consentimento_ativo) atravessa para o prontuário clínico
agregado (ver PacienteService.montar_prontuario_completo).

A rota de anonimizar (POST /<uuid_paciente>/anonimizar) NÃO mora aqui
-- já existe em paciente_pessoal_controller.py, correta e com
id_empresa. Anonimizar é ação sobre PacienteDadosPessoais (LGPD, mas
sobre o dado pessoal em si, não sobre o processo de consentimento) --
fica no controller pessoal, não neste.
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_usuario_sessao, get_id_empresa_sessao
from src.domains.paciente.services import ConsentimentoService

bp = Blueprint("paciente_lgpd", __name__)
_svc = ConsentimentoService()

class LgpdController():
    
    @staticmethod
    @bp.get("/<uuid_paciente>/consentimentos")
    @requer_login
    def listar(uuid_paciente):
        try:
            itens = _svc.listar_por_paciente(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[c.to_dict() for c in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos")
    @requer_papel("medico","enfermeiro")
    def registrar(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.registrar(uuid_paciente, dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=c.to_dict(), message="Consentimento registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos/revogar")
    @requer_papel("medico","enfermeiro")
    def revogar(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.revogar(uuid_paciente, dados.get("motivo"), get_id_empresa_sessao())
            return json_success(data=c.to_dict(), message="Consentimento revogado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # NOVO: registra dispensa de consentimento por urgência/emergência
    # (LGPD art. 11, II, "f" -- tutela da saúde). Não bloqueia nem
    # desbloqueia nada -- nenhum insert clínico verifica consentimento
    # hoje -- só deixa rastreável que a coleta normal foi pulada de
    # propósito, com motivo e responsável registrados.
    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos/dispensar-emergencia")
    @requer_papel("medico", "enfermeiro")
    def dispensar_emergencia(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.dispensar_por_emergencia(
                uuid_paciente, dados, get_id_usuario_sessao(), get_id_empresa_sessao()
            )
            return json_success(data=c.to_dict(), message="Consentimento dispensado por emergência.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)