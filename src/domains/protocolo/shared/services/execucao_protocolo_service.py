# shared/services/execucao_protocolo_service.py
#
# UNICA MUDANCA vs. o arquivo original: buscar_dado_bruto_config passa a
# receber a versao vigente como argumento.
#
#   antes:  dado_bruto = buscar_dado_bruto_config()
#   agora:  dado_bruto = buscar_dado_bruto_config(versao_vigente)
#
# Motivo: o NEWS2 le a config pelo catalogo (nao versionada), mas o
# protocolo-composto pendura a composicao em protocolo_versao -- sem a
# versao em maos, o callback do composto teria que rebuscar a versao
# vigente por conta propria, duplicando a consulta e abrindo uma janela
# em que a versao usada no calculo poderia divergir da gravada em
# id_versao_utilizada. Passando a versao que o Service ja buscou, as
# duas ficam garantidamente a mesma instancia.
#
# Compatibilidade: para o NEWS2 (ou qualquer strategy futura que nao
# precise da versao), o callback so ignora o argumento -- ver o exemplo
# de callback do composto logo abaixo do Service.

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

    def executar_e_persistir(self, id_protocolo_catalogo, id_input, respostas, executor, buscar_dado_bruto_config):
        catalogo = self.repo_catalogo.find_by_id(id_protocolo_catalogo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {id_protocolo_catalogo}")

        if self.repo_execucao.find_por_input_e_protocolo(id_input, id_protocolo_catalogo):
            raise ConflictoError("Este protocolo já foi executado para este input.")

        # "CONTEXTO" = a versão vigente do protocolo, rastreada na execução
        versao_vigente = self.repo_versao.find_vigente(id_protocolo_catalogo)
        if not versao_vigente:
            raise RecursoNaoEncontradoError(f"Nenhuma versão vigente encontrada para o protocolo {id_protocolo_catalogo}")

        strategy = ProtocoloFactory.obter(catalogo.tipo_protocolo)

        # MUDANCA: versao_vigente passa a ser argumento do callback, para
        # composto e NEWS2 compartilharem a mesma instancia de versao que
        # sera gravada em id_versao_utilizada mais abaixo.
        dado_bruto = buscar_dado_bruto_config(versao_vigente)
        if not dado_bruto:
            raise RecursoNaoEncontradoError(f"Configuração não encontrada para o protocolo {id_protocolo_catalogo}")

        estrutura = strategy.carregar_estrutura(dado_bruto)

        try:
            dados_validados = strategy.validar_respostas(estrutura, respostas)  # SCHEMA VALIDA
        except ValueError as ex:
            raise DadosInvalidosError(str(ex))  # DÁ ERRO

        resultado = strategy.executar(estrutura, dados_validados)  # CALCULA

        execucao = InputProtocoloExecucao(
            id_input=id_input,
            id_protocolo_catalogo=id_protocolo_catalogo,
            executor=executor,
            status="concluida" if not resultado.dados_ausentes else "incompleta",
            id_versao_utilizada=versao_vigente.id,   # CONTEXTO salvo aqui
            dados_ausentes_json=resultado.dados_ausentes,
            resultado_calculado_json=resultado.model_dump(),
        )
        return self.repo_execucao.save(execucao)  # SALVA EXECUÇÃO


# ---------------------------------------------------------------------
# Exemplos de callback, para o chamador (controller/rota) que hoje monta
# `buscar_dado_bruto_config`. Nao faz parte da classe -- e so referencia
# de como cada strategy passa a receber o argumento novo.
# ---------------------------------------------------------------------

def callback_news2(repo_escore_config):
    """NEWS2: a config nao e versionada, vive pelo catalogo. Ignora o
    argumento `versao` -- e por isso que o parametro tem default None,
    para nao quebrar uma chamada antiga que ainda nao passe nada."""
    def _buscar(versao=None):
        return repo_escore_config.find_by_protocolo(id_protocolo_catalogo=...)
    return _buscar


def callback_protocolo_composto(repo_composicao):
    """protocolo-composto: PRECISA da versao, porque e nela que
    protocolo_versao.codigo_composicao e a composicao (protocolo_composicao)
    estao penduradas."""
    def _buscar(versao):
        return repo_composicao.carregar_dado_bruto(versao)
    return _buscar