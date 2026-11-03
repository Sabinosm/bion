"""prescricao_exame_service.py

Regras de negócio dos exames prescritos: o médico adiciona, altera e remove
exames do seu rascunho, e a IA propõe exames pelo mesmo caminho de criação.
Toda alteração do médico passa a origem do item e do resultado para "medico".

Antes de qualquer escrita o service exige um rascunho editável (resultado da
empresa, ainda em rascunho, do próprio médico e de atendimento em andamento). O
exame é referenciado pelo UUID público do catálogo, e a origem e o envio de
origem são decididos por quem chama, nunca pelo corpo da requisição. O catálogo
de exames ainda está por planejar, então a busca assume o mesmo padrão dos
outros catálogos (coluna `uuid`).
"""

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from src.models.clinico import PrescricaoExame
from .prescricao_exame_repository import PrescricaoExameRepository
from ..resultado_prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from ..schema_prescricoes import ExamePrescritoIn, ExamePrescritoPatch


class PrescricaoExameService:
    def __init__(self):
        self.repo = PrescricaoExameRepository()
        self.resultado_svc = ResultadoPrescricaoService()

    # ------------------------------------------------------------------
    # Escrita (fluxo do médico)
    # ------------------------------------------------------------------
    def adicionar_exame(self, uuid_resultado: str, item: ExamePrescritoIn, id_empresa: int, id_usuario: int):
        """Médico adiciona um exame ao seu rascunho. Origem do item: 'medico'; o resultado deixa de
        ser 'da IA' (mesma transação).

        Raises:
            RecursoNaoEncontradoError / PermissaoNegadaError / ConflictoError: do rascunho editável.
            RecursoNaoEncontradoError: exame fora do catálogo.
            ConflictoError: exame já consta nesta prescrição.
        """
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        try:
            pe = self.incluir(resultado, item, origem="medico", commit=False)
            self.resultado_svc.marcar_editado(resultado)
            self.repo.confirmar()
        except Exception:
            self.repo.rollback()
            raise
        return pe

    def atualizar_exame(self, uuid_resultado: str, uuid_item: str, patch: ExamePrescritoPatch,
                        id_empresa: int, id_usuario: int):
        """Altera urgência ou justificativa. Se algo mudou, o item e o resultado passam a ser do médico.

        Raises:
            RecursoNaoEncontradoError: item inexistente neste resultado.
        """
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        pe = self._item_do_resultado(uuid_item, resultado)
        mudancas = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if getattr(pe, k) != v}
        if not mudancas:
            return pe
        try:
            for campo, valor in mudancas.items():
                setattr(pe, campo, valor)
            pe.origem_sugestao = "medico"
            self.resultado_svc.marcar_editado(resultado)
            self.repo.confirmar()
        except Exception:
            self.repo.rollback()
            raise
        return pe

    def remover_exame(self, uuid_resultado: str, uuid_item: str, id_empresa: int, id_usuario: int):
        """Remove o exame do rascunho (inclusive sugestão da IA). O resultado passa a ser do médico.

        Raises:
            RecursoNaoEncontradoError: item inexistente neste resultado.
        """
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        pe = self._item_do_resultado(uuid_item, resultado)
        try:
            self.repo.remover(pe, commit=False)
            self.resultado_svc.marcar_editado(resultado)
            self.repo.confirmar()
        except Exception:
            self.repo.rollback()
            raise

    def _item_do_resultado(self, uuid_item: str, resultado):
        pe = self.repo.find_do_resultado(uuid_item, resultado.id)
        if not pe:
            raise RecursoNaoEncontradoError(f"Exame prescrito não encontrado: {uuid_item}")
        return pe

    # ------------------------------------------------------------------
    # Ponto único de criação (médico e IA passam por aqui)
    # ------------------------------------------------------------------
    def incluir(self, resultado, item: ExamePrescritoIn, origem: str,
                id_output_origem: int | None = None, commit: bool = True):
        """Cria o exame no resultado. `origem` e `id_output_origem` são decididos por quem chama,
        nunca pelo body.

        Raises:
            RecursoNaoEncontradoError: exame fora do catálogo.
            ConflictoError: exame já consta nesta prescrição.
        """
        catalogo = self.repo.find_catalogo_por_uuid(item.uuid_exame)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Exame não encontrado no catálogo: {item.uuid_exame}")
        if catalogo.id in self.repo.ids_exame_do_resultado(resultado.id):
            raise ConflictoError("Este exame já consta nesta prescrição.")

        pe = PrescricaoExame(
            id_resultado=resultado.id,
            id_exame=catalogo.id,
            origem_sugestao=origem,
            id_output_origem=id_output_origem,
            **item.model_dump(exclude={"uuid_exame"}),
        )
        return self.repo.save(pe, commit=commit)

    # ------------------------------------------------------------------
    # Estatísticas
    # ------------------------------------------------------------------
    def urgencia_por_origem(self, id_empresa: int, dias: int = 30):
        """Urgência dos exames prescritos, IA x profissional (ver o repository)."""
        return self.repo.urgencia_por_origem(id_empresa=id_empresa, dias=dias)
