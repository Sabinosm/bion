# protocolo_composto/services/protocolo_composto_service.py
"""Ponto de entrada especifico do protocolo-composto: pesquisa (campos),
permissao institucional, e delega a execucao ao orquestrador generico.

Espelha News2Service ponto a ponto. A UNICA diferenca estrutural: a
composicao pendura em protocolo_versao (nao no catalogo), entao tanto
`obter_campos_para_preenchimento` quanto `executar` precisam da VERSAO
VIGENTE, nao so do id_protocolo_catalogo -- por isso este Service usa
ProtocoloVersaoRepository tambem (o News2Service nao precisa, porque
ProtocoloEscoreConfig nao e versionado).

configuracao_protocolo (preferencia pessoal) NAO e gate de execucao --
mesma regra do NEWS2: o unico gate real e empresa_protocolo.ativo.
"""
from src.core.exceptions import DadosInvalidosError, ConflictoError, RecursoNaoEncontradoError
from src.domains.empresa.repository import EmpresaProtocoloRepository
from ..shared.services.execucao_protocolo_service import ExecucaoProtocoloService
from ..shared.repositories.protocolo_versao_repository import ProtocoloVersaoRepository
from .protocolo_composto_repository import ProtocoloComposicaoRepository
from .protocolo_composto_strategy import ProtocoloCompostoStrategy


class ProtocoloCompostoService:

    def __init__(self):
        self.repo_empresa_protocolo = EmpresaProtocoloRepository()
        self.repo_versao = ProtocoloVersaoRepository()
        self.repo_composicao = ProtocoloComposicaoRepository()
        self.strategy = ProtocoloCompostoStrategy()
        self.execucao_svc = ExecucaoProtocoloService()

    # --- 1. Pesquisa ---

    def obter_campos_para_preenchimento(self, id_empresa: int, id_protocolo_catalogo: int):
        self._checar_liberacao_institucional(id_empresa, id_protocolo_catalogo)

        versao_vigente = self.repo_versao.find_vigente(id_protocolo_catalogo)
        if not versao_vigente:
            raise RecursoNaoEncontradoError(
                f"Nenhuma versão vigente encontrada para o protocolo {id_protocolo_catalogo}"
            )

        dado_bruto = self.repo_composicao.carregar_dado_bruto(versao_vigente)
        if not dado_bruto["linhas"]:
            raise RecursoNaoEncontradoError(
                f"Composição não encontrada para o protocolo {id_protocolo_catalogo}"
            )

        estrutura = self.strategy.carregar_estrutura(dado_bruto)
        return self.strategy.campos_esperados(estrutura)

    # --- 2. Permissão antes de executar -- só o gate institucional ---

    def validar_uso_permitido(self, id_empresa: int, id_protocolo_catalogo: int):
        """Único gate real: a empresa precisa ter liberado o protocolo.
        Preferência pessoal (configuracao_protocolo) nunca bloqueia execução."""
        self._checar_liberacao_institucional(id_empresa, id_protocolo_catalogo)

    def _checar_liberacao_institucional(self, id_empresa: int, id_protocolo_catalogo: int):
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
            # NOTA: assinatura com `versao` -- exige o ExecucaoProtocoloService
            # do passo 5 (buscar_dado_bruto_config(versao_vigente)). O
            # News2Service usa `lambda: ...` porque sua config nao e
            # versionada; aqui precisa do argumento porque a composicao
            # pendura em protocolo_versao, nao no catalogo.
            buscar_dado_bruto_config=lambda versao: self.repo_composicao.carregar_dado_bruto(versao),
        )
