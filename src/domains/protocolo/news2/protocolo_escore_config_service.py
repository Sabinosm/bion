"""protocolo_escore_config_service.py

Ponto de entrada específico do NEWS2 (escore ponderado): consulta dos campos
que o protocolo exige, checagem de liberação institucional e execução,
delegada ao orquestrador genérico.

A preferência pessoal do profissional (configuracao_protocolo) não é gate de
execução; o único gate real é a liberação da empresa (empresa_protocolo.ativo),
controlada pelo administrador.
"""
from src.core.exceptions import ConflictoError, RecursoNaoEncontradoError
from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository

from ..shared.services.execucao_protocolo_service import ExecucaoProtocoloService
from .protocolo_escore_config_repository import ProtocoloEscoreConfigRepository
from .protocolo_escore_ponderado import EscorePonderadoStrategy


class News2Service:

    def __init__(self):
        self.repo_empresa_protocolo = EmpresaProtocoloRepository()
        self.repo_config = ProtocoloEscoreConfigRepository()
        self.strategy = EscorePonderadoStrategy()
        self.execucao_svc = ExecucaoProtocoloService()

    def obter_campos_para_preenchimento(self, id_protocolo_catalogo: int):
        """Campos que o protocolo exige. Sem gate de liberação: ver os campos é
        estudo, não uso.

        Raises:
            RecursoNaoEncontradoError: se não houver configuração para o protocolo.
        """
        config = self.repo_config.find_by_protocolo_catalogo(id_protocolo_catalogo)
        if not config:
            raise RecursoNaoEncontradoError(
                f"Configuração NEWS2 não encontrada para protocolo {id_protocolo_catalogo}"
            )

        estrutura = self.strategy.carregar_estrutura(config)
        return self.strategy.campos_esperados(estrutura)

    def validar_uso_permitido(self, id_empresa: int, id_protocolo_catalogo: int):
        """Garante que a empresa liberou o protocolo.

        Raises:
            ConflictoError: se o protocolo não estiver liberado pela instituição.
        """
        vinculo_empresa = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(
            id_empresa, id_protocolo_catalogo
        )
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise ConflictoError("Este protocolo não está liberado pela instituição.")

    def executar(self, id_protocolo_catalogo: int, id_input: int, respostas, executor: int, commit: bool = True):
        """Valida, calcula e persiste a execução. A configuração do NEWS2 não é
        versionada, então o callback ignora a versão recebida."""
        return self.execucao_svc.executar_e_persistir(
            id_protocolo_catalogo=id_protocolo_catalogo,
            id_input=id_input,
            respostas=respostas,
            executor=executor,
            commit=commit,
            tipo_protocolo_esperado=EscorePonderadoStrategy.TIPO_PROTOCOLO,
            buscar_dado_bruto_config=lambda versao=None: self.repo_config.find_by_protocolo_catalogo(
                id_protocolo_catalogo
            ),
        )
