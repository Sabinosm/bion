"""paciente_pessoal_controller.py

Rotas JSON de dados pessoais e cadastrais do paciente (Paciente +
PacienteDadosPessoais). Registrado sob /v1/api/pacientes/pessoal. A contrapartida é
paciente_clinico_controller.py, sob /v1/api/pacientes/clinico: a separação existe porque
pessoal e clínico têm regras de permissão diferentes e cresciam demais misturados.

Toda rota passa a empresa da sessão ao service. Sem isso, os services não teriam como saber
de qual empresa filtrar, e um usuário logado conseguiria ver ou editar pacientes de OUTRA
empresa (o UUID sozinho não prova posse: falha de isolamento de tenant, IDOR).

Permissões (eixo pessoal): ler e corrigir cabem a médico, enfermeiro e admin, porque é gestão
cadastral, não decisão clínica, e o admin lida com isso rotineiramente. Cadastrar e identificar
são de médico ou enfermeiro. Anonimizar (LGPD, direito ao esquecimento) é só do admin: é decisão
de titularidade e compliance da empresa, não ato clínico.

Auditoria: o detalhe e a lista usam acesso auditado (leitura pura não exige step-up, só log de
acesso) e, no erro, devolvem a meta NOOP. Anonimizar é ação sensível (irreversível): exige
step-up e grava o log atômico com a alteração, com `justificativa` obrigatória (tratada como
DELETE lógico); por isso o service roda com commit=False e o commit único (alteração + log) é do
decorator.
"""

from flask import Blueprint, request

from src.core.exceptions import BionException
from src.core.responses import json_success
from src.core.session import (
    requer_login, requer_papel_clinico, requer_admin, requer_admin_ou_papel_clinico,
    get_id_usuario_sessao, get_id_empresa_sessao,
)
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado
from src.domains.paciente.services import PacienteService
from .comum import corpo_json, pode_ver_clinico, resposta_erro, resposta_erro_noop

bp = Blueprint("paciente_pessoal", __name__)
_svc = PacienteService()


def _serializar(paciente, com_pii: bool):
    """Dict do paciente; com `com_pii`, acrescenta os dados pessoais descriptografados em `pessoal`."""
    d = paciente.to_dict()
    if com_pii:
        d["pessoal"] = _svc.dados_pessoais_descriptografados(paciente)
    return d


class PacientePessoalController():

    @staticmethod
    @bp.get("/")
    @requer_login
    @acesso_auditado(recurso="lista de pacientes", operacao="leitura")
    def lista():
        """Pacientes da empresa. A PII só vem em texto claro para médico ou enfermeiro."""
        com_pii = pode_ver_clinico()
        pacientes = _svc.listar(get_id_empresa_sessao())
        return json_success(data=[_serializar(p, com_pii) for p in pacientes])

    @staticmethod
    @bp.post("/<uuid>/identificar")
    @requer_papel_clinico("medico", "enfermeiro")
    def identificar(uuid):
        """Completa o cadastro de um paciente de emergência (mesmo corpo do cadastro)."""
        try:
            p = _svc.identificar(uuid, corpo_json(), get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Paciente identificado.")
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp.get("/resumo")
    @requer_login
    def lista_resumo():
        """Listagem enxuta e paginada (to_dict_few), para telas de busca e seleção de paciente, onde
        não faz sentido carregar o detalhe completo de cada um. Aberta a qualquer logado (decisão
        confirmada): nome e 4 dígitos do CPF servem para confirmar a identidade de quem já se
        apresentou, não para descobrir paciente."""
        pagina = max(request.args.get("pagina", default=0, type=int), 0)
        resultado = _svc.listar_resumo(
            get_id_empresa_sessao(),
            offset=pagina * _svc.POR_PAGINA_RESUMO,
            status=request.args.get("status", type=str),
            sexo_biologico=request.args.get("sexo_biologico", type=str),
        )
        return json_success(data=resultado)

    @staticmethod
    @bp.get("/<uuid>")
    @requer_admin_ou_papel_clinico("enfermeiro", "medico")
    @acesso_auditado(recurso="visualizar dados pessoais paciente", operacao="leitura")
    def detalhe(uuid):
        """Dados cadastrais completos (com PII), com log de acesso."""
        try:
            p = _svc.buscar_por_uuid(uuid, get_id_empresa_sessao())
            return json_success(data=_serializar(p, True))
        except BionException as ex:
            return resposta_erro_noop(ex)

    @staticmethod
    @bp.post("/")
    @requer_papel_clinico("medico", "enfermeiro")
    def cadastrar():
        """Cadastro completo (Paciente + dados pessoais, numa transação)."""
        try:
            p = _svc.cadastrar(corpo_json(), get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Paciente cadastrado.", status=201)
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp.put("/<uuid>")
    @requer_admin_ou_papel_clinico("medico", "enfermeiro")
    def atualizar_pessoal(uuid):
        """Corrige o cadastro, só os campos enviados (`null` limpa os opcionais)."""
        try:
            p = _svc.atualizar_pessoal(uuid, corpo_json(), get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Dados pessoais atualizados.")
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp.post("/<uuid>/anonimizar")
    @requer_admin
    @acao_sensivel(acao="anonimizar_paciente", tabela="paciente_dados_pessoais")
    def anonimizar(uuid):
        """Direito ao esquecimento (LGPD): remove os dados pessoais e mantém o registro clínico
        anonimizado. Só admin. Irreversível: step-up, log atômico e justificativa no corpo
        (`motivo` ou `justificativa`)."""
        dados = corpo_json()
        try:
            p = _svc.anonimizar(uuid, get_id_empresa_sessao(), commit=False)
            return json_success(data=p.to_dict(), message="Paciente anonimizado."), {
                "id_registro": p.id,
                "uuid_registro": p.uuid,
                "operacao": "DELETE",
                "campo_alterado": "dados_pessoais",
                "justificativa": dados.get("motivo") or dados.get("justificativa"),
            }
        except BionException as ex:
            return resposta_erro(ex), {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}
