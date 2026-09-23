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

ATUALIZADO: `detalhe()` trocou de `acao_sensivel` para `acesso_auditado`
-- decisão confirmada, mesmo motivo de paciente_clinico_controller.py:
leitura pura não precisa de step-up, só de log de acesso.

ATUALIZADO: `anonimizar()` passou a usar `acao_sensivel` -- decisão
confirmada. É uma ação de LGPD irreversível (remove PacienteDadosPessoais
mantendo o registro clínico anonimizado) que antes não tinha nenhum
rastro de auditoria nem exigência de reconfirmação de identidade. Agora
exige step-up e registra log atômico com a alteração; `justificativa`
é obrigatória (operação tratada como DELETE lógico) -- o corpo da
requisição precisa trazer o motivo da anonimização.
"""

from flask import Blueprint, request, session

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_login, requer_papel_clinico, get_id_usuario_sessao, get_id_empresa_sessao, requer_admin
from src.domains.paciente.services import PacienteService
from src.domains.auditoria.acaoSensivel import acao_sensivel, acesso_auditado

bp = Blueprint("paciente_pessoal", __name__)
_svc = PacienteService()


def _pode_ver_clinico() -> bool:
    return session.get("funcao_clinica") in ("medico", "enfermeiro")


def _serializar(paciente, com_pii: bool):
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


    # ATUALIZADO: usa acesso_auditado, não acao_sensivel -- leitura não
    # exige step-up; só fica registrado como LogAcesso.
    @staticmethod
    @bp.get("/<uuid>")
    @requer_login
    @acesso_auditado(recurso="visualizar dados pessoais paciente", operacao="leitura")
    def detalhe(uuid):
        com_pii = _pode_ver_clinico()
        try:
            p = _svc.buscar_por_uuid(uuid, get_id_empresa_sessao())
            return json_success(data=_serializar(p, com_pii))
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.post("/")
    @requer_papel_clinico("medico", "enfermeiro")
    def cadastrar():
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc.cadastrar(dados, get_id_usuario_sessao(), get_id_empresa_sessao())
            return json_success(data=_serializar(p, True), message="Paciente cadastrado.", status=201)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)


    @staticmethod
    @bp.put("/<uuid>")
    @requer_papel_clinico("medico", "enfermeiro", "admin")
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
    #
    # ATUALIZADO: passou a exigir step-up (acao_sensivel) + log atômico
    # -- decisão confirmada, ação irreversível de LGPD.
    #
    # ATENÇÃO: _svc.anonimizar agora aceita commit (corrigido em
    # paciente_service.py) -- comitava incondicionalmente antes, o que
    # quebrava a atomicidade que acao_sensivel precisa. Chamado aqui
    # com commit=False; o commit único (alteração + log) acontece no
    # decorator.
    @staticmethod
    @bp.post("/<uuid>/anonimizar")
    @requer_admin
    @acao_sensivel(acao="anonimizar_paciente", tabela="paciente_dados_pessoais")
    def anonimizar(uuid):
        dados = request.get_json(silent=True) or {}
        try:
            p = _svc.anonimizar(uuid, get_id_empresa_sessao(), commit=False)
            resposta = json_success(data=p.to_dict(), message="Paciente anonimizado.")
            return resposta, {
                "id_registro": p.id,
                "uuid_registro": p.uuid,
                "operacao": "DELETE",
                "campo_alterado": "dados_pessoais",
                "justificativa": dados.get("motivo") or dados.get("justificativa"),
            }
        except BionException as ex:
            resposta = json_error(ex.message, ex.status_code)
            return resposta, {"id_registro": None, "uuid_registro": uuid, "operacao": "NOOP"}