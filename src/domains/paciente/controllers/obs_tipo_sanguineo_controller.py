"""obs_tipo_sanguineo_controller.py

Rotas JSON do tipo sanguíneo do paciente, que é INSERT-ONLY: a leitura (vigente e
histórico), em `bp`, e o registro de uma nova observação, em `bp_escrita`, aninhado no
atendimento:

    /<uuid_atendimento>/pacientes/<uuid_paciente>/tipo-sanguineo

`bp_escrita` deve ser registrado com o MESMO url_prefix do blueprint de atendimento. A
leitura é de médico ou enfermeiro da empresa. Quem pode escrever é decidido pelo service
(checagem comum de escrita clínica). Não há rota de correção nem de remoção: corrigir é
registrar uma nova observação.
"""

from flask import Blueprint

from src.core.exceptions import BionException
from src.core.responses import json_success
from src.core.session import requer_papel_clinico, get_id_empresa_sessao
from src.domains.paciente.services import ObservacaoTipoSanguineoService
from .comum import autor_clinico, corpo_json, resposta_erro

bp = Blueprint("tipo_sanguineo", __name__)
bp_escrita = Blueprint("tipo_sanguineo_escrita", __name__)
_svc = ObservacaoTipoSanguineoService()

_ESC = "/<uuid_atendimento>/pacientes/<uuid_paciente>/tipo-sanguineo"


class ObservacaoTipoSanguineoController():

    # ------------------------------------------------------------ LEITURA
    @staticmethod
    @bp.get("/<uuid_paciente>/tipo-sanguineo")
    @requer_papel_clinico("medico", "enfermeiro")
    def tipo_vigente(uuid_paciente):
        """Tipo vigente; data=null se nunca foi registrado."""
        try:
            obs = _svc.tipo_vigente(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=obs.to_dict() if obs else None)
        except BionException as ex:
            return resposta_erro(ex)

    @staticmethod
    @bp.get("/<uuid_paciente>/tipo-sanguineo/historico")
    @requer_papel_clinico("medico", "enfermeiro")
    def historico_tipo_sanguineo(uuid_paciente):
        """Todas as observações, da mais recente para a mais antiga."""
        try:
            itens = _svc.historico(uuid_paciente, get_id_empresa_sessao())
            return json_success(data=[o.to_dict() for o in itens])
        except BionException as ex:
            return resposta_erro(ex)

    # ------------------------------------------------------------ ESCRITA
    @staticmethod
    @bp_escrita.post(_ESC)
    @requer_papel_clinico("medico", "enfermeiro")
    def registrar_tipo_sanguineo(uuid_atendimento, uuid_paciente):
        """Registra uma nova observação de tipo sanguíneo."""
        try:
            o = _svc.registrar_tipo_sanguineo(uuid_atendimento, uuid_paciente, corpo_json(),
                                              autor_clinico())
            return json_success(data=o.to_dict(), message="Tipo sanguíneo registrado.", status=201)
        except BionException as ex:
            return resposta_erro(ex)
