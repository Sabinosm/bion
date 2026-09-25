"""Orquestra os 9 passos: busca -> factory -> valida -> executa -> persiste.
Nunca sabe qual família de protocolo está rodando por trás.
"""
from ..repositories.protocolo_catalogo_repository import RepositorioProtocoloCatalogo
from ....protocolo.news2.repositories.protocolo_escore_config_repository import ProtocoloEscoreConfigRepository
from ..strategy.protocolo_factory import ProtocoloFactory
from ..schemas.schema_resultado import SchemaResultado


class ServicoExecucaoProtocolo:
    def __init__(
        self,
        repo_catalogo: RepositorioProtocoloCatalogo,
        repo_escore_config: ProtocoloEscoreConfigRepository,
    ):
        self._repo_catalogo = repo_catalogo
        self._repo_escore_config = repo_escore_config

    def executar(self, id_protocolo_catalogo: int, respostas: dict) -> SchemaResultado:
        catalogo = self._repo_catalogo.buscar_por_id(id_protocolo_catalogo)
        if catalogo is None:
            raise ValueError("Protocolo não encontrado")

        strategy = ProtocoloFactory.obter(catalogo.tipo_protocolo)

        dado_bruto = self._buscar_config_bruta(catalogo.tipo_protocolo, id_protocolo_catalogo)
        estrutura = strategy.carregar_estrutura(dado_bruto)

        dados_validados = strategy.validar_respostas(estrutura, respostas)
        resultado = strategy.executar(estrutura, dados_validados)

        # persistência de input_protocolo_execucao fica a cargo de um repo próprio,
        # chamado aqui na sequência (omitido para não misturar responsabilidades)

        return resultado

    def _buscar_config_bruta(self, tipo_protocolo: str, id_protocolo_catalogo: int):
        if tipo_protocolo == "escore-ponderado":
            return self._repo_escore_config.buscar_por_protocolo(id_protocolo_catalogo)
        raise ValueError(f"Repository não implementado para tipo_protocolo='{tipo_protocolo}'")