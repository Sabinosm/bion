"""service.py

Monta o PacienteService juntando, numa única classe, os mixins por
responsabilidade (leitura, cadastro e atualização). Quem importa o service não
percebe a divisão.

Este service NÃO toca em db.session: todo commit, flush e rollback é delegado ao
PacienteRepository. Os métodos de escrita aceitam `commit`: com True (padrão) a
operação confirma sozinha e desfaz sozinha em caso de erro; com False fica
pendente (flush) para o chamador comitar junto com outras escritas (abrir
consulta com paciente e consentimento, ou uma ação sensível com a alteração e o
log). Com commit=False o rollback é de quem controla a transação.
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
    """Regras de negócio de Paciente (ver o docstring do módulo)."""

    def __init__(self):
        self.repo = PacienteRepository()
        self.tipo_sanguineo_repo = ObservacaoTipoSanguineoRepository()
