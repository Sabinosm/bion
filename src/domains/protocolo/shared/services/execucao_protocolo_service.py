"""Orquestrador genérico de execução de protocolo: valida permissão,
delega o cálculo à Strategy (via Factory), persiste em InputProtocoloExecucao.

Não sabe qual família de protocolo está rodando -- só fala com
ProtocoloFactory e com os repositórios comuns (catálogo, input_execucao,
versao). A parte específica do NEWS2 (carregar_estrutura, validar_respostas,
executar) mora inteiramente na Strategy.
"""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository
from ..repositories.protocolo_versao_repository import ProtocoloVersaoRepository
from ..repositories.input_protocolo_execucao_repository import InputProtocoloExecucaoRepository
from ..strategy.protocolo_factory import ProtocoloFactory
from src.models.clinico import InputProtocoloExecucao


class ExecucaoProtocoloService:

    def __init__(self):
        self.repo_catalogo = ProtocoloCatalogoRepository()
        self.repo_versao = ProtocoloVersaoRepository()
        self.repo_execucao = InputProtocoloExecucaoRepository()

    def executar_e_persistir(
        self,
        id_protocolo_catalogo: int,
        id_input: int,
        respostas: dict,
        executor: int,
        buscar_dado_bruto_config,
    ) -> InputProtocoloExecucao:
        """
        buscar_dado_bruto_config: callable que devolve o Model de configuração
        específico da família (ex: ProtocoloEscoreConfig), já resolvido por
        quem chama -- este Service não sabe em qual tabela de config buscar,
        isso é responsabilidade de cada News2Service/MtsService/etc.
        """
        catalogo = self.repo_catalogo.find_by_id(id_protocolo_catalogo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {id_protocolo_catalogo}")

        if self.repo_execucao.find_por_input_e_protocolo(id_input, id_protocolo_catalogo):
            raise ConflictoError("Este protocolo já foi executado para este input.")

        versao_vigente = self.repo_versao.find_vigente(id_protocolo_catalogo)
        if not versao_vigente:
            raise RecursoNaoEncontradoError(f"Nenhuma versão vigente encontrada para o protocolo {id_protocolo_catalogo}")

        strategy = ProtocoloFactory.obter(catalogo.tipo_protocolo)

        dado_bruto = buscar_dado_bruto_config()
        if not dado_bruto:
            raise RecursoNaoEncontradoError(f"Configuração não encontrada para o protocolo {id_protocolo_catalogo}")

        estrutura = strategy.carregar_estrutura(dado_bruto)

        try:
            dados_validados = strategy.validar_respostas(estrutura, respostas)
        except ValueError as ex:
            raise DadosInvalidosError(str(ex))

        resultado = strategy.executar(estrutura, dados_validados)

        execucao = InputProtocoloExecucao(
            id_input=id_input,
            id_protocolo_catalogo=id_protocolo_catalogo,
            executor=executor,
            status="concluida" if not resultado.dados_ausentes else "incompleta",
            id_versao_utilizada=versao_vigente.id,   # <- corrigido: era .id_versao
            dados_ausentes_json=resultado.dados_ausentes,
            resultado_calculado_json=resultado.model_dump(),
        )
        return self.repo_execucao.save(execucao)