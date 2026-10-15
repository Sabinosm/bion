from src.models import db
from src.core.exceptions import RecursoNaoEncontradoError
from src.models.clinico import PrescricaoExame
from .prescricao_exame_repository import PrescricaoExameRepository
from ..resultado_prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from ..schema_prescricoes import ExamePrescritoIn


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
        """Médico adiciona um exame ao seu rascunho. Origem fixa: 'medico'."""
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        return self.incluir(resultado, item, origem="medico")

    def remover_exame(self, uuid_resultado: str, uuid_item: str, id_empresa: int, id_usuario: int):
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        pe = self.repo.find_do_resultado(uuid_item, resultado.id)
        if not pe:
            raise RecursoNaoEncontradoError(f"Exame prescrito não encontrado: {uuid_item}")
        self.repo.delete(pe.id)

    # ------------------------------------------------------------------
    # Ponto único de criação (médico e IA passam por aqui)
    # ------------------------------------------------------------------
    def incluir(self, resultado, item: ExamePrescritoIn, origem: str,
                id_output_origem: int | None = None, commit: bool = True):
        """origem e id_output_origem são decididos por quem chama, nunca pelo body."""
        from src.models.catalogos import CatalogoExames

        if not db.session.get(CatalogoExames, item.id_exame):
            raise RecursoNaoEncontradoError(f"Exame não encontrado no catálogo: {item.id_exame}")

        pe = PrescricaoExame(
            id_resultado=resultado.id,
            origem_sugestao=origem,
            id_output_origem=id_output_origem,
            **item.model_dump(),
        )
        return self.repo.save(pe, commit=commit)