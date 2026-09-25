"""Regras de negócio da execução do protocolo NEWS2."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..strategy.protocolo_escore_ponderado import ProtocoloEscorePonderadoStrategy
from ..repositories.protocolo_escore_config_repository import ProtocoloEscoreConfigRepository
from ...shared.repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository


class News2Service:
    """Orquestra a execução do NEWS2: busca config, valida respostas, calcula resultado."""

    def __init__(self):
        self.repo_catalogo = ProtocoloCatalogoRepository()
        self.repo_config = ProtocoloEscoreConfigRepository()
        self.strategy = ProtocoloEscorePonderadoStrategy()

    def executar(self, id_protocolo_catalogo: int, respostas: dict):
        """
        Executa o NEWS2 para um conjunto de respostas.

        Raises:
            RecursoNaoEncontradoError: se o protocolo ou sua config não existirem.
            DadosInvalidosError: se as respostas contiverem campos não declarados.
        """
        catalogo = self.repo_catalogo.find_by_id(id_protocolo_catalogo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {id_protocolo_catalogo}")

        config = self.repo_config.find_by_protocolo_catalogo(id_protocolo_catalogo)
        if not config:
            raise RecursoNaoEncontradoError(f"Configuração NEWS2 não encontrada para protocolo {id_protocolo_catalogo}")

        estrutura = self.strategy.carregar_estrutura(config)

        try:
            dados_validados = self.strategy.validar_respostas(estrutura, respostas)
        except ValueError as ex:
            raise DadosInvalidosError(str(ex))

        resultado = self.strategy.executar(estrutura, dados_validados)
        return resultado