# news2/services/news2_service.py

from src.core.exceptions import DadosInvalidosError, ConflictoError, RecursoNaoEncontradoError
from src.domains.empresa.repository import EmpresaProtocoloRepository
from ..shared.services.execucao_protocolo_service import ExecucaoProtocoloService
from .protocolo_escore_config_repository import ProtocoloEscoreConfigRepository
from .protocolo_escore_ponderado import EscorePonderadoStrategy
from src.domains.configuracao.repository import ConfiguracaoRepository

class News2Service:
    """Ponto de entrada específico do NEWS2: pesquisa (campos), permissão
    institucional, e delega a execução ao orquestrador genérico.

    configuracao_protocolo NÃO é gate de execução -- é só preferência pessoal
    de atalho (protocolo aparece em destaque na consulta). O único gate real
    é empresa_protocolo.ativo, controlado pelo admin.
    """

    def __init__(self):
        self.repo_empresa_protocolo = EmpresaProtocoloRepository()
        self.repo_config = ProtocoloEscoreConfigRepository()
        self.strategy = EscorePonderadoStrategy()
        self.execucao_svc = ExecucaoProtocoloService()

    # --- 1. Pesquisa ---

    def obter_campos_para_preenchimento(self, id_empresa: int, id_protocolo_catalogo: int):
        vinculo_empresa = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(id_empresa, id_protocolo_catalogo)
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise ConflictoError("Este protocolo não está liberado pela instituição.")

        config = self.repo_config.find_by_protocolo_catalogo(id_protocolo_catalogo)
        if not config:
            raise RecursoNaoEncontradoError(f"Configuração NEWS2 não encontrada para protocolo {id_protocolo_catalogo}")

        estrutura = self.strategy.carregar_estrutura(config)
        return self.strategy.campos_esperados(estrutura)

    # --- 2. Permissão antes de executar -- só o gate institucional ---

    def validar_uso_permitido(self, id_empresa: int, id_protocolo_catalogo: int):
        """Único gate real: a empresa precisa ter liberado o protocolo.
        Preferência pessoal (configuracao_protocolo) nunca bloqueia execução."""
        vinculo_empresa = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(id_empresa, id_protocolo_catalogo)
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise ConflictoError("Este protocolo não está liberado pela instituição.")

    # --- 3+4+5+6. Schema valida -> calcula -> salva execução -> versão usada (contexto) ---

    def executar(self, id_protocolo_catalogo: int, id_input: int, respostas: dict, executor: int):
        return self.execucao_svc.executar_e_persistir(
            id_protocolo_catalogo=id_protocolo_catalogo,
            id_input=id_input,
            respostas=respostas,
            executor=executor,
            buscar_dado_bruto_config=lambda: self.repo_config.find_by_protocolo_catalogo(id_protocolo_catalogo),
        )