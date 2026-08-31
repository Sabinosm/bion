"""
Rotas JSON de dados clínicos do paciente (Paciente + alergias +
doenças crônicas + medicamentos em uso + tipo sanguíneo). Registrado
sob /v1/api/pacientes/clinico.

ALTERADO: GET /<uuid> agora devolve o prontuário clínico COMPLETO --
agrega Paciente.to_dict() + alergias + doenças crônicas + medicamentos
em uso + um booleano consentimento_ativo (ver PacienteService.
montar_prontuario_completo). Decisão confirmada: essa agregação só
acontece aqui, nunca em listagem (lista()/lista_resumo() do controller
pessoal continuam leves, sem N+1 queries por paciente).

Consentimento fica fora do agregado como objeto completo -- é sobre
titularidade/LGPD, não dado clínico -- só entra o booleano; o
histórico de termos vive em LgpdController. Tipo sanguíneo no agregado
é só o valor atual (via Paciente.tipo_sanguineo); o histórico de
observações continua em endpoint próprio (tipo-sanguineo/*).

Contrapartida: paciente_pessoal_controller.py, sob
/v1/api/pacientes/pessoal.

Duas rotas para tipo_sanguineo refletem a separação decidida
(registrar = novo exame/histórico; corrigir = editar um registro
específico por engano de digitação) -- semântica própria, não um
campo dentro de um PUT genérico.

Toda rota passa id_empresa (da sessão do usuário logado) pro service,
pelo mesmo motivo do controller pessoal: sem isso, um usuário logado
conseguiria ver ou editar paciente de outra empresa (isolamento de
tenant / IDOR).

Permissões deste arquivo (eixo clínico): ler e escrever ficam por
padrão com médico/enfermeiro -- é trabalho clínico. Admin tem
permissão técnica para PUT /<uuid> (status, falecido, data_obito),
pensado pro caso de apoio pontual pedido pelo médico responsável, mas
essa gravação específica fica registrada em auditoria por ser exceção
ao fluxo esperado, não rotina -- ver PacienteService.
registrar_escrita_clinica_excepcional. Tipo sanguíneo (histórico de
exame) fica só com médico/enfermeiro, sem essa exceção para admin.
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_usuario_sessao, get_id_empresa_sessao
from src.domains.paciente.services import PacienteService, ObservacaoTipoSanguineoService

bp = Blueprint("paciente_clinico", __name__)
_svc = PacienteService()
_svc_tipo_sanguineo = ObservacaoTipoSanguineoService()


def _pode_ver_clinico() -> bool:
    return session.get("tipo_usuario") in ("medico", "enfermeiro")


def _serializar_clinico(paciente):
    """Só o dado clínico do paciente -- ao contrário do controller
    pessoal, esta rota nunca inclui PII (nome, cpf, telefone...)."""
    return paciente.to_dict()

class PacienteClinicoController():

    # ALTERADO: detalhe() agora devolve o prontuário completo
    # (paciente + alergias + doenças crônicas + medicamentos em uso +
    # consentimento_ativo como booleano) -- só aqui, nunca em listagem
    @staticmethod
    @bp.get("/<uuid>")
    @requer_papel("medico", "enfermeiro")
    def detalhe(uuid):
        try:
            prontuario = _svc.montar_prontuario_completo(uuid, get_id_empresa_sessao())
            return json_success(data=prontuario)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Separado de atualizar_pessoal -- status, falecido, data_obito.
    # Admin tem permissão técnica (caso o médico responsável peça apoio
    # pontual), mas essa gravação específica é registrada em auditoria
    # por ser exceção, não fluxo normal.
    @staticmethod
    @bp.put("/<uuid>")
    @requer_papel("medico", "enfermeiro", "admin")
    def atualizar_clinico(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc.atualizar_clinico(uuid, dados, get_id_empresa_sessao())
            if not _pode_ver_clinico():
                _svc.registrar_escrita_clinica_excepcional(
                    uuid, get_id_usuario_sessao(), acao="atualizar_clinico"
                )
            return json_success(data=_serializar_clinico(p), message="Dados clínicos atualizados.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Registra novo exame/resultado de tipo sanguíneo (preserva histórico)
    @staticmethod
    @bp.post("/<uuid>/tipo-sanguineo")
    @requer_papel("medico", "enfermeiro")
    def registrar_tipo_sanguineo(uuid):
        dados = request.get_json(silent=True) or {}
        if not dados.get("tipo_sanguineo"):
            return json_error("tipo_sanguineo é obrigatório.", 422)
        try:
            p = _svc_tipo_sanguineo.registrar_tipo_sanguineo(
                uuid, dados["tipo_sanguineo"], get_id_usuario_sessao(), get_id_empresa_sessao()
            )
            return json_success(data=_serializar_clinico(p), message="Tipo sanguíneo registrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Corrige uma observação específica (erro de digitação, não novo exame)
    @staticmethod
    @bp.put("/<uuid>/tipo-sanguineo/<uuid_observacao>")
    @requer_papel("medico", "enfermeiro")
    def corrigir_tipo_sanguineo(uuid, uuid_observacao):
        dados = request.get_json(silent=True) or {}
        if not dados.get("tipo_sanguineo"):
            return json_error("tipo_sanguineo é obrigatório.", 422)
        try:
            obs = _svc_tipo_sanguineo.corrigir_tipo_sanguineo(
                uuid, uuid_observacao, dados["tipo_sanguineo"], get_id_empresa_sessao()
            )
            return json_success(data=obs.to_dict(), message="Tipo sanguíneo corrigido.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Remove um registro criado por engano (ex: paciente errado, duplicata).
    # É clínico (histórico de exame), não gestão cadastral -- sem
    # exceção para admin aqui.
    @staticmethod
    @bp.delete("/<uuid>/tipo-sanguineo/<uuid_observacao>")
    @requer_papel("medico", "enfermeiro")
    def remover_tipo_sanguineo(uuid, uuid_observacao):
        try:
            _svc_tipo_sanguineo.remover_tipo_sanguineo(uuid, uuid_observacao, get_id_empresa_sessao())
            return json_success(message="Observação de tipo sanguíneo removida.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)