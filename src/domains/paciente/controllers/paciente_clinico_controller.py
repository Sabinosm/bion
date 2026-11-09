"""paciente_clinico_controller.py

Rotas JSON de dados clínicos do paciente: prontuário completo, status clínico (ativo ou
inativo), óbito (registrar e reverter) e a listagem enxuta com busca. Registrado sob
/v1/api/pacientes/clinico. A contrapartida é paciente_pessoal_controller.py, sob
/v1/api/pacientes/pessoal. O tipo sanguíneo tem controller próprio (insert-only), em
obs_tipo_sanguineo_controller.py.

O detalhe devolve o prontuário clínico COMPLETO: Paciente.to_dict() mais alergias, doenças
crônicas, medicamentos em uso, interações, o tipo sanguíneo vigente, o resumo clínico e um
booleano `consentimento_ativo`. Essa agregação só acontece aqui, nunca em listagem (a lista e o
resumo continuam leves, sem N+1 por paciente). O consentimento fica fora do agregado como
objeto (é titularidade/LGPD, não dado clínico); o histórico de termos vive no LgpdController.

Toda rota passa a empresa da sessão ao service, pelo mesmo motivo do controller pessoal: sem
isso, um usuário logado conseguiria ver ou editar paciente de outra empresa (isolamento de
tenant, IDOR).

Permissões (eixo clínico): ler e escrever ficam, por padrão, com médico e enfermeiro, porque é
trabalho clínico. O admin tem permissão técnica para alterar o status e registrar o óbito, pensada
para apoio pontual pedido pelo médico responsável; essa gravação específica é uma exceção ao
fluxo esperado e fica registrada em auditoria. O controller passa `auditar_excecao_por` ao
service, que grava a alteração e a linha de auditoria na MESMA transação.

Óbito: o PUT só alterna o status entre ativo e inativo (falecido, data_obito e status="obito" são
rejeitados com 422). Registrar e reverter o óbito têm rotas próprias, para status, falecido e
data_obito nunca ficarem dessincronizados; reverter é ação sensível (step-up, justificativa
obrigatória e log atômico). As rotas auditadas devolvem a meta NOOP nos erros.
"""

from flask import Blueprint, request

from src.core.exceptions import BionException
from src.core.responses import json_success, json_error
from src.core.session import (
    requer_papel_clinico, requer_admin_ou_papel_clinico,
    get_id_usuario_sessao, get_id_empresa_sessao,
)
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado
from src.domains.paciente.services import PacienteService
from .comum import corpo_json, pode_ver_clinico, resposta_erro, resposta_erro_noop

bp = Blueprint("paciente_clinico", __name__)
_svc = PacienteService()


def _id_admin_excecao():
    """id do usuário quando quem grava NÃO é médico nem enfermeiro (ou seja, admin em escrita
    excepcional); None caso contrário. O service grava escrita e auditoria na mesma transação com
    esse valor."""
    return None if pode_ver_clinico() else get_id_usuario_sessao()


def _serializar_clinico(paciente):
    """Só o dado clínico do paciente: ao contrário do controller pessoal, esta rota nunca inclui
    PII (nome, cpf, telefone...)."""
    return paciente.to_dict()


class PacienteClinicoController():

    @staticmethod
    @bp.get("/resumo")
    @requer_papel_clinico("enfermeiro", "medico")
    def lista_resumo():
        """Listagem enxuta e paginada, com busca opcional `q` (CPF completo ou parte do nome) e
        filtros `status` e `sexo_biologico`."""
        pagina = max(request.args.get("pagina", default=0, type=int), 0)
        resultado = _svc.listar_resumo(
            get_id_empresa_sessao(),
            offset=pagina * _svc.POR_PAGINA_RESUMO,
            status=request.args.get("status", type=str),
            sexo_biologico=request.args.get("sexo_biologico", type=str),
            q=request.args.get("q", type=str),
        )
        return json_success(data=resultado)

    @staticmethod
    @bp.get("/<uuid>")
    @requer_admin_ou_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="visualizar prontuario", operacao="leitura")
    def detalhe(uuid):
        """Prontuário clínico completo (leitura pura: só log de acesso, sem step-up)."""
        try:
            prontuario = _svc.montar_prontuario_completo(uuid, get_id_empresa_sessao())
            return json_success(data=prontuario)
        except BionException as ex:
            return resposta_erro_noop(ex)

    @staticmethod
    @bp.put("/<uuid>")
    @requer_admin_ou_papel_clinico("medico", "enfermeiro")
    def atualizar_clinico(uuid):
        """Só `status`, entre ativo e inativo. Admin como exceção, com auditoria."""
        try:
            p = _svc.atualizar_clinico(
                uuid, corpo_json(), get_id_empresa_sessao(),
                auditar_excecao_por=_id_admin_excecao(),
            )
            return json_success(data=_serializar_clinico(p), message="Dados clínicos atualizados.")
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp.post("/<uuid>/obito")
    @requer_admin_ou_papel_clinico("medico", "enfermeiro")
    @acesso_auditado(recurso="marcar obito", operacao="escrita")
    def marcar_obito(uuid):
        """Registra o óbito: status="obito", falecido=True e data_obito sempre juntos. Mesma regra
        de papel de atualizar_clinico (admin só como exceção, com auditoria)."""
        try:
            p = _svc.marcar_obito(
                uuid, corpo_json().get("data_obito"), get_id_empresa_sessao(),
                auditar_excecao_por=_id_admin_excecao(),
            )
            return json_success(data=_serializar_clinico(p), message="Óbito registrado.")
        except BionException as ex:
            return resposta_erro_noop(ex)

    @staticmethod
    @bp.post("/<uuid>/obito/reverter")
    @requer_admin_ou_papel_clinico("medico", "enfermeiro")
    @acao_sensivel(acao="reverter_obito", tabela="paciente")
    def reverter_obito(uuid):
        """Desfaz um óbito marcado por engano. Ação sensível: step-up, justificativa obrigatória e
        log atômico com a alteração.
        Corpo: {"justificativa": "...", "status_destino": "ativo"|"inativo"}"""
        dados = corpo_json()
        justificativa = dados.get("justificativa")
        if not justificativa:
            resposta = json_error("justificativa é obrigatória.", 422, erros={"justificativa": "obrigatória."})
            return resposta, {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}
        try:
            p = _svc.reverter_obito(
                uuid, get_id_empresa_sessao(),
                dados.get("status_destino", "ativo"), commit=False,
            )
            return json_success(data=_serializar_clinico(p), message="Óbito revertido."), {
                "id_registro": p.id,
                "uuid_registro": p.uuid,
                "operacao": "UPDATE",
                "campo_alterado": "falecido",
                "justificativa": justificativa,
            }
        except BionException as ex:
            return resposta_erro(ex), {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}
