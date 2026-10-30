"""execucao_protocolo_service.py

Orquestrador genérico de execução de protocolos. Dado um protocolo e um
input, carrega a versão vigente e a configuração, valida as respostas, calcula
o resultado pela estratégia da família e persiste a execução registrando a
versão utilizada. Não conhece nenhuma família concreta: toda a diferença entre
elas está na estratégia e no callback que busca a configuração.
"""
from typing import Any, Callable

from src.core.exceptions import BionException, ConflictoError, DadosInvalidosError, RecursoNaoEncontradoError
from src.models.clinico import InputProtocoloExecucao

from ..repositories.input_protocolo_execucao_repository import InputProtocoloExecucaoRepository
from ..repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository
from ..repositories.protocolo_versao_repository import ProtocoloVersaoRepository
from ..strategy.protocolo_factory import ProtocoloFactory


class ExecucaoProtocoloService:

    def __init__(self):
        self.repo_catalogo = ProtocoloCatalogoRepository()
        self.repo_versao = ProtocoloVersaoRepository()
        self.repo_execucao = InputProtocoloExecucaoRepository()

    def executar_e_persistir(
        self,
        id_protocolo_catalogo: int,
        id_input: int,
        respostas: dict | Callable[[Any, Any], dict],
        executor: int,
        buscar_dado_bruto_config: Callable[[Any], Any],
        tipo_protocolo_esperado: str | None = None,
        commit: bool = True,
    ) -> InputProtocoloExecucao:
        """Executa o protocolo sobre o input e grava a execução.

        Args:
            respostas: dict ou callable(estrutura, strategy) -> dict, para quem
                só conhece os campos depois de carregar a estrutura.
            executor: ID do usuário que executou.
            buscar_dado_bruto_config: callable(versao_vigente) -> dado bruto da
                configuração. Recebe a versão vigente já buscada aqui para que a
                versão usada no cálculo seja a mesma gravada em
                `id_versao_utilizada`. Quem não precisa da versão (ex.: NEWS2,
                cuja configuração não é versionada) a ignora.
            tipo_protocolo_esperado: `tipo_protocolo` que a família chamadora
                atende. Impede que a rota de uma família execute um protocolo de
                outra.
            commit: com False, apenas faz flush e deixa a transação com o chamador.

        Raises:
            RecursoNaoEncontradoError: protocolo, versão vigente ou configuração ausente.
            ConflictoError: protocolo inativo no catálogo ou já executado para este input.
            DadosInvalidosError: protocolo de outro tipo ou respostas inválidas.
            ConfiguracaoProtocoloInvalidaError: configuração cadastrada do protocolo inconsistente (500).
        """
        catalogo = self.repo_catalogo.find_by_id(id_protocolo_catalogo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {id_protocolo_catalogo}")

        if tipo_protocolo_esperado and catalogo.tipo_protocolo != tipo_protocolo_esperado:
            raise DadosInvalidosError(
                f"O protocolo '{catalogo.sigla}' não é do tipo '{tipo_protocolo_esperado}'."
            )
        if catalogo.status != "ativo":
            raise ConflictoError(f"O protocolo '{catalogo.sigla}' não está ativo no catálogo.")

        if self.repo_execucao.find_por_input_e_protocolo(id_input, id_protocolo_catalogo):
            raise ConflictoError("Este protocolo já foi executado para este input.")

        versao_vigente = self.repo_versao.find_vigente(id_protocolo_catalogo)
        if not versao_vigente:
            raise RecursoNaoEncontradoError(
                f"Nenhuma versão vigente encontrada para o protocolo {id_protocolo_catalogo}"
            )

        strategy = ProtocoloFactory.obter(catalogo.tipo_protocolo)

        dado_bruto = buscar_dado_bruto_config(versao_vigente)
        if not dado_bruto:
            raise RecursoNaoEncontradoError(
                f"Configuração não encontrada para o protocolo {id_protocolo_catalogo}"
            )

        estrutura = strategy.carregar_estrutura(dado_bruto)

        if callable(respostas):
            respostas = respostas(estrutura, strategy)

        try:
            dados_validados = strategy.validar_respostas(estrutura, respostas)
        except BionException:
            raise
        except ValueError as ex:
            raise DadosInvalidosError(str(ex))

        resultado = strategy.executar(estrutura, dados_validados)

        execucao = InputProtocoloExecucao(
            id_input=id_input,
            id_protocolo_catalogo=id_protocolo_catalogo,
            executor=executor,
            status="incompleta" if resultado.dados_ausentes else "concluida",
            id_versao_utilizada=versao_vigente.id,
            dados_ausentes_json=resultado.dados_ausentes,
            resultado_calculado_json=resultado.model_dump(),
        )
        return self.repo_execucao.save(execucao, commit=commit)
