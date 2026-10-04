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
from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository
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

    def obter_campos_para_preenchimento(self, id_protocolo_catalogo: int):
        """União das variáveis de todos os módulos. SEM gate de liberação: ver
        os campos é estudo, não uso -- o gate real fica em validar_uso_permitido."""
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

    def obter_composicao(self, id_protocolo_catalogo: int) -> dict:
        """Estrutura do composto para a página de detalhe (só leitura): agregação,
        gatilhos e, por módulo, papel/família/saída/explicação/referência e os
        campos DAQUELE módulo, já completos (nome, tipo, unidade, opções, faixa).
        Não expõe configuracao_json (a lógica interna do módulo)."""
        versao = self.repo_versao.find_vigente(id_protocolo_catalogo)
        if not versao:
            raise RecursoNaoEncontradoError(
                f"Nenhuma versão vigente encontrada para o protocolo {id_protocolo_catalogo}"
            )
        if not versao.composicoes:
            raise RecursoNaoEncontradoError(
                f"Composição não encontrada para o protocolo {id_protocolo_catalogo}"
            )

        config = versao.composicao_config
        modulos = []
        for comp in versao.composicoes:  # já ordenadas por `ordem` (relationship)
            mv = comp.modulo_versao
            m = mv.modulo
            modulos.append({
                "papel": comp.papel,
                "grupo_agregacao": comp.grupo_agregacao,
                "ordem": comp.ordem,
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
                # Campo completo (VariavelClinica) + obrigatoriedade neste módulo.
                "campos": [self._montar_campo(cm) for cm in mv.campos],  # já ordenados por `ordem`
            })

        return {
            "versao": {
                "numero_versao": versao.numero_versao,
                "vigente_desde": versao.vigente_desde.isoformat() if versao.vigente_desde else None,
            },
            "agregacao": config.agregacao if config else "nenhuma",
            "regra_gatilho": config.regra_gatilho_json if config else None,
            "modulos": modulos,
        }

    @staticmethod
    def _montar_campo(campo_modulo) -> dict:
        """ModuloVersaoCampo -> dict de exibição, com a VariavelClinica embutida.
        tipo_dado: numerico | categorico | booleano. Sem codigo_loinc (não é exibição)."""
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