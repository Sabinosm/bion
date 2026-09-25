# news2/services/news2_service.py

from src.core.exceptions import DadosInvalidosError, ConflictoError, RecursoNaoEncontradoError
from src.domains.empresa.repository import EmpresaProtocoloRepository
from ..shared.services.execucao_protocolo_service import ExecucaoProtocoloService
from .protocolo_escore_config_repository import ProtocoloEscoreConfigRepository
from .protocolo_escore_ponderado import EscorePonderadoStrategy
from src.domains.configuracao.repository import ConfiguracaoRepository


class News2Service:
    """Ponto de entrada específico do NEWS2: pesquisa (campos), permissão,
    e delega a execução ao orquestrador genérico."""

    def __init__(self):
        self.repo_empresa_protocolo = EmpresaProtocoloRepository()
        self.repo_configuracao = ConfiguracaoRepository()
        self.repo_config = ProtocoloEscoreConfigRepository()
        self.strategy = EscorePonderadoStrategy()
        self.execucao_svc = ExecucaoProtocoloService()

    # --- 1. Pesquisa ---

    def obter_campos_para_preenchimento(self, id_empresa: int, id_protocolo_catalogo: int):
        """Só checa liberação institucional -- não exige configuracao_protocolo,
        que é escolha pessoal de USO, não de leitura/estudo."""
        vinculo_empresa = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(id_empresa, id_protocolo_catalogo)
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise ConflictoError("Este protocolo não está liberado pela instituição.")

        config = self.repo_config.find_by_protocolo_catalogo(id_protocolo_catalogo)
        if not config:
            raise RecursoNaoEncontradoError(f"Configuração NEWS2 não encontrada para protocolo {id_protocolo_catalogo}")

        estrutura = self.strategy.carregar_estrutura(config)
        return self.strategy.campos_esperados(estrutura)

    # --- 2. Permissão completa, antes de executar ---

    def validar_uso_permitido(self, id_empresa: int, id_usuario: int, id_protocolo_catalogo: int):
        vinculo_empresa = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(id_empresa, id_protocolo_catalogo)
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise ConflictoError("Este protocolo não está liberado pela instituição.")

        cfg = self.repo_configuracao.find_by_usuario(id_usuario)
        if not cfg:
            raise DadosInvalidosError("Configuração do usuário não encontrada.")

        vinculo_pessoal = self.repo_configuracao.find_protocolo(cfg.id, id_protocolo_catalogo)
        if not vinculo_pessoal or not vinculo_pessoal.em_uso:
            raise ConflictoError("Você não tem este protocolo habilitado. Habilite-o em Configurações antes de usar.")

    # --- 3+4+5+6. Schema valida -> calcula -> salva execução -> versão usada (contexto) ---

    def executar(self, id_protocolo_catalogo: int, id_input: int, respostas: dict, executor: int):
        return self.execucao_svc.executar_e_persistir(
            id_protocolo_catalogo=id_protocolo_catalogo,
            id_input=id_input,
            respostas=respostas,
            executor=executor,
            buscar_dado_bruto_config=lambda: self.repo_config.find_by_protocolo_catalogo(id_protocolo_catalogo),
        )