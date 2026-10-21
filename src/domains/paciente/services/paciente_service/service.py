"""PacienteService: junta os mixins por responsabilidade numa única classe.

A classe pública continua sendo `PacienteService`; quem importa de
`...services.paciente_service` não percebe a divisão.
"""
from ...repositories import (
    PacienteRepository,
    ObservacaoTipoSanguineoRepository,
)

from .leitura import LeituraMixin
from .cadastro import CadastroMixin
from .atualizacao import AtualizacaoMixin


class PacienteService(
    LeituraMixin,
    CadastroMixin,
    AtualizacaoMixin,
):
    """Regras de negócio de Paciente.

    TRANSAÇÃO: este service NÃO toca em db.session. Todo commit, flush e
    rollback é delegado a PacienteRepository (ver `confirmar`, `save`,
    `rollback`). Os métodos de escrita aceitam `commit`:
      - commit=True  (padrão): a operação confirma sozinha.
      - commit=False: fica pendente (flush) para o chamador comitar junto
        com outras escritas -- ConsultaService.abrir (paciente + consulta
        + consentimento) e acao_sensivel (alteração + log) dependem disso.
    Com commit=False o rollback em caso de erro é responsabilidade de quem
    controla a transação; com commit=True o service desfaz sozinho.
    """

    def __init__(self):
        self.repo = PacienteRepository()
        self.tipo_sanguineo_repo = ObservacaoTipoSanguineoRepository()
