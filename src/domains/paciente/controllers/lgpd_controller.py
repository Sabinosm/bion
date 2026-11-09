"""lgpd_controller.py

Rotas JSON do consentimento LGPD do paciente, no fluxo MANUAL. Registrado sob
/v1/api/pacientes/lgpd (mesmo prefixo do controller de assinatura digital).

Consentimento diz respeito ao paciente, mas o PROCESSO (termos, canal de coleta,
histórico, revogação) não é pessoal nem clínico: é titularidade/LGPD, domínio à parte.
Só o RESULTADO (consentimento ativo) atravessa para o prontuário clínico agregado.

Divisão entre os dois controllers de consentimento:
- ESTE: histórico, registro manual (papel, portal, totem), revogação e dispensa por
  emergência. O canal 'presencial-digital' é rejeitado aqui pelo schema.
- consentimento_digital_controller: assinatura por QR code (sessão, token, PDF assinado,
  comprovante).

A rota de anonimizar (POST /<uuid_paciente>/anonimizar) NÃO mora aqui: está em
paciente_pessoal_controller.py (age sobre o dado pessoal, não sobre o processo de
consentimento). Revogar é ação sensível (step-up e log atômico); registrar e dispensar
são acessos auditados. Nas rotas auditadas o erro devolve a meta NOOP.
"""

from flask import Blueprint

from src.core.exceptions import BionException
from src.core.responses import json_success
from src.core.session import (
    requer_login, requer_papel_clinico, get_id_usuario_sessao, get_id_empresa_sessao,
)
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado
from src.domains.paciente.services import ConsentimentoService
from .comum import corpo_json, resposta_erro, resposta_erro_noop

bp = Blueprint("paciente_lgpd", __name__)
_svc = ConsentimentoService()


class LgpdController:
    """Rotas do fluxo manual de consentimento (histórico, registro, revogação, dispensa)."""

    @staticmethod
    @bp.get("/<uuid_paciente>/consentimentos")
    @requer_login
    def listar(uuid_paciente):
        """Histórico de consentimentos do paciente."""
        try:
            itens = _svc.listar_por_paciente(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[c.to_dict() for c in itens])
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="registrar consentimento", operacao="escrita")
    def registrar(uuid_paciente):
        """Registro manual. canal_coleta: presencial-papel | portal-online | totem."""
        try:
            c = _svc.registrar(uuid_paciente, corpo_json(), get_id_usuario_sessao(), get_id_empresa_sessao())
            return (json_success(data=c.to_dict(), message="Consentimento registrado.", status=201),
                    {"uuid_paciente": uuid_paciente})
        except BionException as ex:
            return resposta_erro_noop(ex)

    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos/revogar")
    @requer_papel_clinico("medico", "enfermeiro")
    @acao_sensivel(acao="revogar_consentimento", tabela="consentimento")
    def revogar(uuid_paciente):
        """Revoga o consentimento ativo, com motivo (ação sensível: step-up e log atômico)."""
        try:
            c = _svc.revogar(uuid_paciente, corpo_json(), get_id_empresa_sessao(), commit=False)
            return json_success(data=c.to_dict(), message="Consentimento revogado."), {
                "id_registro": c.id,
                "uuid_registro": c.uuid,
                "operacao": "UPDATE",
                "campo_alterado": "status",
                "valor_novo": "revogado",
            }
        except BionException as ex:
            return resposta_erro(ex), {"id_registro": None, "uuid_registro": uuid_paciente, "operacao": "NOOP"}

    @staticmethod
    @bp.post("/<uuid_paciente>/consentimentos/dispensar-emergencia")
    @requer_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="dispensar consentimento por emergência", operacao="escrita")
    def dispensar_emergencia(uuid_paciente):
        """Dispensa de consentimento por urgência ou emergência (LGPD art. 11, II, "f", tutela da
        saúde). Não bloqueia nem desbloqueia nada: deixa rastreável que a coleta normal foi pulada
        de propósito, com motivo e responsável."""
        try:
            c = _svc.dispensar_por_emergencia(
                uuid_paciente, corpo_json(), get_id_usuario_sessao(), get_id_empresa_sessao()
            )
            return (json_success(data=c.to_dict(), message="Consentimento dispensado por emergência.",
                                 status=201), {"uuid_paciente": uuid_paciente})
        except BionException as ex:
            return resposta_erro_noop(ex)
