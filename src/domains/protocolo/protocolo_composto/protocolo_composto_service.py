"""protocolo_composto_service.py

Ponto de entrada específico do protocolo composto: consulta dos campos e da
composição (pesquisa), checagem de liberação institucional e execução,
delegada ao orquestrador genérico.

Diferença em relação ao NEWS2: a composição é pendurada na versão vigente do
protocolo (protocolo_versao), não no catálogo, então a consulta e a execução
precisam da versão vigente. A preferência pessoal (configuracao_protocolo) não
é gate de execução; o único gate real é a liberação da empresa
(empresa_protocolo.ativo).
"""
from src.core.exceptions import ConflictoError, RecursoNaoEncontradoError
from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository

from ..shared.repositories.protocolo_versao_repository import ProtocoloVersaoRepository
from ..shared.services.execucao_protocolo_service import ExecucaoProtocoloService
from .protocolo_composto_repository import ProtocoloComposicaoRepository
from .protocolo_composto_strategy import ProtocoloCompostoStrategy


class ProtocoloCompostoService:

    def __init__(self):
        self.repo_empresa_protocolo = EmpresaProtocoloRepository()
        self.repo_versao = ProtocoloVersaoRepository()
        self.repo_composicao = ProtocoloComposicaoRepository()
        self.strategy = ProtocoloCompostoStrategy()
        self.execucao_svc = ExecucaoProtocoloService()

    def obter_campos_para_preenchimento(self, id_protocolo_catalogo: int):
        """União das variáveis de todos os módulos. Sem gate de liberação: ver os
        campos é estudo, não uso.

        Raises:
            RecursoNaoEncontradoError: sem versão vigente ou sem composição.
        """
        versao_vigente = self._versao_vigente_ou_erro(id_protocolo_catalogo)

        dado_bruto = self.repo_composicao.carregar_dado_bruto(versao_vigente)
        if not dado_bruto["linhas"]:
            raise RecursoNaoEncontradoError(
                f"Composição não encontrada para o protocolo {id_protocolo_catalogo}"
            )

        estrutura = self.strategy.carregar_estrutura(dado_bruto)
        return self.strategy.campos_esperados(estrutura)

    def obter_composicao(self, id_protocolo_catalogo: int) -> dict:
        """Estrutura do composto para a página de detalhe (somente leitura):
        agregação, gatilhos e, por módulo, papel/família/saída/explicação/
        referência e os campos daquele módulo. Não expõe `configuracao_json`
        (a lógica interna do módulo).

        Raises:
            RecursoNaoEncontradoError: sem versão vigente ou sem composição.
        """
        versao = self._versao_vigente_ou_erro(id_protocolo_catalogo)
        linhas = self.repo_composicao.carregar_composicao(versao.id)
        if not linhas:
            raise RecursoNaoEncontradoError(
                f"Composição não encontrada para o protocolo {id_protocolo_catalogo}"
            )

        config = self.repo_composicao.carregar_config(versao.id)
        return {
            "versao": {
                "numero_versao": versao.numero_versao,
                "vigente_desde": versao.vigente_desde.isoformat() if versao.vigente_desde else None,
            },
            "agregacao": config.agregacao if config else "nenhuma",
            "regra_gatilho": config.regra_gatilho_json if config else None,
            # o repository já devolve as linhas ordenadas por `ordem`
            "modulos": [self._montar_modulo(comp) for comp in linhas],
        }

    def validar_uso_permitido(self, id_empresa: int, id_protocolo_catalogo: int):
        """Garante que a empresa liberou o protocolo. A preferência pessoal nunca
        bloqueia a execução.

        Raises:
            ConflictoError: se o protocolo não estiver liberado pela instituição.
        """
        vinculo_empresa = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(
            id_empresa, id_protocolo_catalogo
        )
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise ConflictoError("Este protocolo não está liberado pela instituição.")

    def executar(self, id_protocolo_catalogo: int, id_input: int, respostas, executor: int, commit: bool = True):
        """Valida, calcula e persiste a execução. O callback recebe a versão vigente
        do orquestrador, garantindo que a composição usada no cálculo seja a da
        versão gravada em `id_versao_utilizada`."""
        return self.execucao_svc.executar_e_persistir(
            id_protocolo_catalogo=id_protocolo_catalogo,
            id_input=id_input,
            respostas=respostas,
            executor=executor,
            commit=commit,
            tipo_protocolo_esperado=ProtocoloCompostoStrategy.TIPO_PROTOCOLO,
            buscar_dado_bruto_config=self.repo_composicao.carregar_dado_bruto,
        )

    def _versao_vigente_ou_erro(self, id_protocolo_catalogo: int):
        versao = self.repo_versao.find_vigente(id_protocolo_catalogo)
        if not versao:
            raise RecursoNaoEncontradoError(
                f"Nenhuma versão vigente encontrada para o protocolo {id_protocolo_catalogo}"
            )
        return versao

    def _montar_modulo(self, composicao) -> dict:
        """Uma linha da composição no formato de exibição (módulo, versão, explicação e campos)."""
        mv = composicao.modulo_versao
        m = mv.modulo
        return {
            "papel": composicao.papel,
            "grupo_agregacao": composicao.grupo_agregacao,
            "ordem": composicao.ordem,
            "modulo": {
                "uuid": m.uuid,
                "nome_modulo": m.nome_modulo,
                "sigla": m.sigla,
                "tipo_modulo": m.tipo_modulo,
                "familia_calculo": m.familia_calculo,
                "tipo_saida": m.tipo_saida,
                "descricao": m.descricao,
                "referencia_bibliografica": m.referencia_bibliografica,
            },
            "numero_versao": mv.numero_versao,
            "explicacao": mv.explicacao_json,
            # `campos` já vem ordenado por `ordem` (relationship)
            "campos": [self._montar_campo(cm) for cm in mv.campos],
        }

    @staticmethod
    def _montar_campo(campo_modulo) -> dict:
        """ModuloVersaoCampo -> dict de exibição, com a VariavelClinica embutida e a
        obrigatoriedade no módulo. tipo_dado: numerico | categorico | booleano.
        Não inclui codigo_loinc (não é exibição)."""
        v = campo_modulo.variavel
        return {
            "codigo": v.codigo if v else None,
            "nome": v.nome if v else None,
            "tipo_dado": v.tipo_dado if v else None,
            "unidade": v.unidade if v else None,
            "opcoes": v.opcoes_json if v else None,
            "valor_min": float(v.valor_min) if v and v.valor_min is not None else None,
            "valor_max": float(v.valor_max) if v and v.valor_max is not None else None,
            "obrigatorio": campo_modulo.obrigatorio,
            "ordem": campo_modulo.ordem,
        }
