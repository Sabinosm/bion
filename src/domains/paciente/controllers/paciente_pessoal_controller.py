"""
Rotas JSON de dados pessoais/cadastrais do paciente (Paciente +
PacienteDadosPessoais). Registrado sob /v1/api/pacientes/pessoal.

Contrapartida: paciente_clinico_controller.py, sob
/v1/api/pacientes/clinico -- separação decidida porque pessoal e
clínico têm regras de permissão diferentes (ver nota abaixo) e cresciam
demais misturados num único arquivo.

PII (nome, cpf, telefone, email, endereco) so e devolvida em texto claro
para medico/enfermeiro; qualquer outro perfil autenticado ve apenas os
dados clinicos nao-identificaveis do Paciente.

Toda rota passa id_empresa (da sessão do usuário logado) pro service.
Sem isso, listar()/buscar_por_uuid()/etc. não têm como saber de qual
empresa filtrar -- e um usuário logado conseguiria ver ou editar
pacientes de OUTRA empresa, já que o UUID sozinho não prova posse
(falha de isolamento de tenant / IDOR).

Permissões deste arquivo (eixo pessoal): ler e corrigir cabem a
médico, enfermeiro e admin -- é gestão cadastral, não decisão clínica,
e o admin lida com isso rotineiramente (mesma razão de existir
"Gerenciamento"/"Pacientes" no nav dele). Anonimizar (LGPD, direito ao
esquecimento) fica só com admin -- é decisão de titularidade/
compliance da empresa, não ato clínico; tirado do médico de propósito.
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel, get_id_usuario_sessao, get_id_empresa_sessao
from src.domains.paciente.services import PacienteService

bp = Blueprint("paciente_pessoal", __name__)
_svc = PacienteService()


def _pode_ver_clinico() -> bool:
    return session.get("tipo_usuario") in ("medico", "enfermeiro")


def _serializar(paciente, com_pii: bool):
    d = paciente.to_dict()
    if com_pii:
        d["pessoal"] = _svc.dados_pessoais_descriptografados(paciente)
    return d

class PacientePessoalController():

    @staticmethod
    @bp.get("/")
    @requer_login
    def lista():
        com_pii = _pode_ver_clinico()
        pacientes = _svc.listar(get_id_empresa_sessao())
        return json_success(data=[_serializar(p, com_pii) for p in pacientes])


    # Listagem enxuta e paginada (to_dict_few) -- pra telas de
    # busca/seleção de paciente, onde não faz sentido carregar o
    # detalhe completo de cada um. Aberta a qualquer logado (decisão
    # confirmada): nome + 4 dígitos do CPF serve pra confirmar
    # identidade de quem já se apresentou, não pra descobrir paciente.
    @staticmethod
    @bp.get("/resumo")
    @requer_login
    def lista_resumo():
        status = request.args.get("status", type=str)
        sexo_biologico = request.args.get("sexo_biologico", type=str)
        pagina = request.args.get("pagina", default=0, type=int)

        resultado = _svc.listar_resumo(
            get_id_empresa_sessao(),
            offset=int(pagina * 8),
            status=status,
            sexo_biologico=sexo_biologico,
        )
        return json_success(data=resultado)


    @staticmethod
    @bp.get("/<uuid>")
    @requer_login
    def detalhe(uuid):
        com_pii = _pode_ver_clinico()
        try:
            p = _svc.buscar_por_uuid(uuid, get_id_empresa_sessao())
            return json_success(data=_serializar(p, com_pii))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/")
    @requer_papel("medico", "enfermeiro")
    def cadastrar():
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc.cadastrar(dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Paciente cadastrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.put("/<uuid>")
    @requer_papel("medico", "enfermeiro", "admin")
    def atualizar_pessoal(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc.atualizar_pessoal(uuid, dados, get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Dados pessoais atualizados.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    # Exercício do direito ao esquecimento (LGPD) -- remove
    # PacienteDadosPessoais mantendo o registro clínico anonimizado.
    # Só admin: decisão de titularidade/compliance, não ato clínico.
    @staticmethod
    @bp.post("/<uuid>/anonimizar")
    @requer_papel("admin")
    def anonimizar(uuid):
        try:
            p = _svc.anonimizar(uuid, get_id_empresa_sessao())
            return json_success(data=p.to_dict(), message="Paciente anonimizado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)