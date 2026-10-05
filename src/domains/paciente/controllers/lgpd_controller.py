"""
Rotas JSON de consentimento LGPD do paciente -- fluxo MANUAL. Registrado sob
/v1/api/pacientes/lgpd (mesmo prefixo do controller de assinatura digital).

Decisão: consentimento diz respeito ao paciente, mas o PROCESSO (termos, canal
de coleta, histórico, revogação) não é pessoal nem clínico -- é titularidade/
LGPD, domínio à parte. Só o RESULTADO (consentimento ativo) atravessa para o
prontuário clínico agregado (ver PacienteService.montar_prontuario_completo).

Divisão entre os dois controllers de consentimento:
- ESTE: histórico, registro manual (papel, portal, totem), revogação e dispensa
  por emergência. O canal 'presencial-digital' é rejeitado aqui pelo schema.
- consentimento_digital_controller: assinatura por QR code (sessão, token,
  PDF assinado, comprovante).

A rota de anonimizar (POST /<uuid_paciente>/anonimizar) NÃO mora aqui -- está
em paciente_pessoal_controller.py (age sobre o dado pessoal, não sobre o
processo de consentimento).

Dados do usuário logado: get_id_usuario_sessao(), get_id_empresa_sessao().
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import (
    requer_login,
    requer_papel_clinico,
    get_id_usuario_sessao,
    get_id_empresa_sessao,
)
from src.domains.paciente.services import ConsentimentoService
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado

bp = Blueprint("paciente_lgpd", __name__)
_svc = ConsentimentoService()

class LgpdController:
    """Rotas do fluxo manual de consentimento (histórico, registro, revogação, dispensa)."""

    @staticmethod
    @bp.get("/<uuid_paciente>/consentimentos")
    @requer_login
    @acesso_auditado(recurso="lista de consentimentos", operacao="leitura")
    def listar(uuid_paciente):
        try:
            itens = _svc.listar_por_paciente(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[c.to_dict() for c in itens])
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="registrar consentimento", operacao="escrita")
    def registrar(uuid_paciente):
        """Registro manual. canal_coleta: presencial-papel | portal-online | totem."""
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.registrar(uuid_paciente, dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=c.to_dict(), message="Consentimento registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos/revogar")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel(acao="revogar_consentimento", tabela="consentimento")
    def revogar(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.revogar(uuid_paciente, dados, get_id_empresa_sessao(), commit=False)
            resposta = json_success(data=c.to_dict(), message="Consentimento revogado.")
            return resposta, {
                "id_registro": c.id,
                "uuid_registro": c.uuid,
                "operacao": "UPDATE",
                "campo_alterado": "status",       # antes dizia 'consentimento_ativo' (campo inexistente)
                "valor_novo": "revogado",
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid_paciente, "operacao": "NOOP"}


    # Dispensa de consentimento por urgência/emergência (LGPD art. 11, II, "f" --
    # tutela da saúde). Não bloqueia nem desbloqueia nada; deixa rastreável que a
    # coleta normal foi pulada de propósito, com motivo e responsável.
    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos/dispensar-emergencia")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="dispensar consentimento por emergência", operacao="escrita")
    def dispensar_emergencia(uuid_paciente):
        dados = request.get_json(silent=True) or {}
        try:
            c = _svc.dispensar_por_emergencia(
                uuid_paciente, dados, get_id_usuario_sessao(), get_id_empresa_sessao()
            )
            return json_success(data=c.to_dict(), message="Consentimento dispensado por emergência.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)