"""prescricao_service.py

Regras de negócio dos medicamentos prescritos: o médico adiciona, altera e
remove medicamentos do seu rascunho, e a IA propõe itens pelo mesmo caminho de
criação. Toda alteração do médico passa a origem do item e do resultado para
"medico", e a sugestão original da IA continua registrada no envio à IA.

Antes de qualquer escrita o service exige um rascunho editável (resultado da
empresa, ainda em rascunho, do próprio médico e de atendimento em andamento). O
medicamento é referenciado pelo UUID público do catálogo, não pode repetir no
mesmo resultado, e a origem e o envio de origem são decididos por quem chama,
nunca pelo corpo da requisição. A adição devolve também os alertas de
interação do conjunto atual do rascunho.
"""

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from src.models.clinico import Prescricao
from src.domains.medicamentos.repository import CatalogoMedicamentosRepository
from .prescricao_repository import PrescricaoRepository
from .resultado_prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from .prescricao_validacao_service import PrescricaoValidacaoService
from .schema_prescricoes import MedicamentoPrescritoIn, MedicamentoPrescritoPatch


class PrescricaoService:
    def __init__(self):
        self.prescricao_repo = PrescricaoRepository()
        self.catalogo_repo = CatalogoMedicamentosRepository()
        self.resultado_svc = ResultadoPrescricaoService()
        self.validacao_svc = PrescricaoValidacaoService()

    # ------------------------------------------------------------------
    # Escrita (fluxo do médico)
    # ------------------------------------------------------------------
    def adicionar_medicamento(self, uuid_resultado: str, item: MedicamentoPrescritoIn,
                              id_empresa: int, id_usuario: int):
        """Médico adiciona um medicamento ao seu rascunho. Origem do item: 'medico'; o resultado
        deixa de ser 'da IA' (mesma transação).

        Retorna (prescricao, verificacao): verificacao = {"alertas", "cobertura"} com as
        interações do conjunto atual de medicamentos do rascunho, entre si e com os
        medicamentos que o paciente já usa.

        Raises:
            RecursoNaoEncontradoError / PermissaoNegadaError / ConflictoError: do rascunho editável.
            RecursoNaoEncontradoError: medicamento fora do catálogo.
            ConflictoError: medicamento já consta na prescrição.
        """
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        try:
            p = self.incluir(resultado, item, origem="medico", commit=False)
            self.resultado_svc.marcar_editado(resultado)
            self.prescricao_repo.confirmar()
        except Exception:
            self.prescricao_repo.rollback()
            raise
        verificacao = self.validacao_svc.verificar_interacoes(
            self.prescricao_repo.ids_catalogo_do_resultado(resultado.id),
            self.validacao_svc.ids_em_uso(resultado, id_empresa),
        )
        return p, verificacao

    def atualizar_medicamento(self, uuid_resultado: str, uuid_item: str, patch: MedicamentoPrescritoPatch,
                              id_empresa: int, id_usuario: int):
        """Altera dose, frequência, duração ou orientações. Se algo mudou, o item e o resultado
        passam a ser do médico (a sugestão original da IA continua no Output_bion).

        Raises:
            RecursoNaoEncontradoError: item inexistente neste resultado.
        """
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        p = self._item_do_resultado(uuid_item, resultado)
        mudancas = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if getattr(p, k) != v}
        if not mudancas:
            return p
        try:
            for campo, valor in mudancas.items():
                setattr(p, campo, valor)
            p.origem_sugestao = "medico"
            self.resultado_svc.marcar_editado(resultado)
            self.prescricao_repo.confirmar()
        except Exception:
            self.prescricao_repo.rollback()
            raise
        return p

    def remover_medicamento(self, uuid_resultado: str, uuid_item: str, id_empresa: int, id_usuario: int):
        """Remove o item do rascunho (inclusive sugestão da IA). O resultado passa a ser do médico.

        Raises:
            RecursoNaoEncontradoError: item inexistente neste resultado.
        """
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        p = self._item_do_resultado(uuid_item, resultado)
        try:
            self.prescricao_repo.remover(p, commit=False)
            self.resultado_svc.marcar_editado(resultado)
            self.prescricao_repo.confirmar()
        except Exception:
            self.prescricao_repo.rollback()
            raise

    def _item_do_resultado(self, uuid_item: str, resultado):
        p = self.prescricao_repo.find_do_resultado(uuid_item, resultado.id)
        if not p:
            raise RecursoNaoEncontradoError(f"Medicamento prescrito não encontrado: {uuid_item}")
        return p

    # ------------------------------------------------------------------
    # Ponto único de criação (médico e IA passam por aqui)
    # ------------------------------------------------------------------
    def incluir(self, resultado, item: MedicamentoPrescritoIn, origem: str,
                id_output_origem: int | None = None, commit: bool = True):
        """Cria o item no resultado. `origem` e `id_output_origem` são decididos por quem chama,
        nunca pelo body.

        Raises:
            RecursoNaoEncontradoError: medicamento fora do catálogo.
            ConflictoError: medicamento já consta nesta prescrição.
        """
        catalogo = self.catalogo_repo.find_by_uuid(item.uuid_catalogo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Medicamento não encontrado no catálogo: {item.uuid_catalogo}")
        if catalogo.id in self.prescricao_repo.ids_catalogo_do_resultado(resultado.id):
            raise ConflictoError(f"O medicamento '{catalogo.principio_ativo}' já consta nesta prescrição.")

        p = Prescricao(
            id_resultado_prescricao=resultado.id,
            id_catalogo=catalogo.id,
            origem_sugestao=origem,
            id_output_origem=id_output_origem,
            **item.model_dump(exclude={"uuid_catalogo"}),  # só campos clínicos
        )
        return self.prescricao_repo.save(p, commit=commit)

    # ------------------------------------------------------------------
    # Estatísticas
    # ------------------------------------------------------------------
    def top_por_classe(self, id_empresa: int, dias: int = 30, limite: int = 10):
        """Ranking das classes farmacêuticas mais prescritas (ver o repository)."""
        return self.prescricao_repo.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)

    def top_principios_ativos_por_classe(self, id_empresa: int, classe: str, dias: int = 30, limite: int = 10):
        """Princípios ativos mais prescritos dentro de uma classe (detalhe do ranking)."""
        return self.prescricao_repo.top_principios_ativos_por_classe(
            id_empresa=id_empresa, classe=classe, dias=dias, limite=limite
        )
