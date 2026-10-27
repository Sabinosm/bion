from src.core.exceptions import RecursoNaoEncontradoError
from src.models import db
from src.models.clinico import PrescricaoExame
from .prescricao_exame_repository import PrescricaoExameRepository
from ..resultado_prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from ..schema_prescricoes import ExamePrescritoIn, ExamePrescritoPatch


class PrescricaoExameService:
    def __init__(self):
        self.repo = PrescricaoExameRepository()
        self.resultado_svc = ResultadoPrescricaoService()

    # --- D3: Urgência de exames -- IA vs. profissional ---
    def urgencia_por_origem(self, id_empresa: int, dias: int = 30):
        return self.repo.urgencia_por_origem(id_empresa=id_empresa, dias=dias)

    # ------------------------------------------------------------------
    # Escrita (fluxo do médico)
    # ------------------------------------------------------------------
    def adicionar_exame(self, uuid_resultado: str, item: ExamePrescritoIn, id_empresa: int, id_usuario: int):
        """Médico adiciona um exame ao seu rascunho. Origem do item: 'medico'; o resultado deixa de
        ser 'da IA' (mesma transação)."""
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        try:
            pe = self.incluir(resultado, item, origem="medico", commit=False)
            self.resultado_svc.marcar_editado(resultado)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return pe

    def atualizar_exame(self, uuid_resultado: str, uuid_item: str, patch: ExamePrescritoPatch,
                        id_empresa: int, id_usuario: int):
        """Altera urgência ou justificativa. Se algo mudou, o item e o resultado passam a ser do médico."""
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        pe = self.repo.find_do_resultado(uuid_item, resultado.id)
        if not pe:
            raise RecursoNaoEncontradoError(f"Exame prescrito não encontrado: {uuid_item}")
        mudancas = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if getattr(pe, k) != v}
        if not mudancas:
            return pe
        try:
            for campo, valor in mudancas.items():
                setattr(pe, campo, valor)
            pe.origem_sugestao = "medico"
            self.resultado_svc.marcar_editado(resultado)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return pe

    def remover_exame(self, uuid_resultado: str, uuid_item: str, id_empresa: int, id_usuario: int):
        """Remove o exame do rascunho (inclusive sugestão da IA). O resultado passa a ser do médico."""
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        pe = self.repo.find_do_resultado(uuid_item, resultado.id)
        if not pe:
            raise RecursoNaoEncontradoError(f"Exame prescrito não encontrado: {uuid_item}")
        try:
            db.session.delete(pe)
            self.resultado_svc.marcar_editado(resultado)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    # ------------------------------------------------------------------
    # Ponto único de criação (médico e IA passam por aqui)
    # ------------------------------------------------------------------
    def incluir(self, resultado, item: ExamePrescritoIn, origem: str,
                id_output_origem: int | None = None, commit: bool = True):
        """origem e id_output_origem são decididos por quem chama, nunca pelo body."""
        # Ajustar para o repositório do catálogo de exames quando ele existir
        # (hoje assume o mesmo padrão dos outros catálogos: coluna `uuid`).
        from src.models.catalogos import CatalogoExames

        catalogo = CatalogoExames.query.filter_by(uuid=item.uuid_exame).first()
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Exame não encontrado no catálogo: {item.uuid_exame}")

        pe = PrescricaoExame(
            id_resultado=resultado.id,
            id_exame=catalogo.id,
            origem_sugestao=origem,
            id_output_origem=id_output_origem,
            **item.model_dump(exclude={"uuid_exame"}),
        )
        return self.repo.save(pe, commit=commit)