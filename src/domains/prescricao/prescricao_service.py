from src.models import db
from src.core.exceptions import RecursoNaoEncontradoError
from src.models.clinico import Prescricao
from .prescricao_repository import PrescricaoRepository
from .resultado_prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from .schema_prescricoes import MedicamentoPrescritoIn


class PrescricaoService:
    def __init__(self):
        self.prescricao_repo = PrescricaoRepository()
        self.resultado_svc = ResultadoPrescricaoService()

    # ------------------------------------------------------------------
    # Escrita (fluxo do médico)
    # ------------------------------------------------------------------
    def adicionar_medicamento(self, uuid_resultado: str, item: MedicamentoPrescritoIn,
                              id_empresa: int, id_usuario: int):
        """Médico adiciona um medicamento ao seu rascunho. Origem fixa: 'medico'."""
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        return self.incluir(resultado, item, origem="medico")

    def remover_medicamento(self, uuid_resultado: str, uuid_item: str, id_empresa: int, id_usuario: int):
        resultado = self.resultado_svc.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        p = self.prescricao_repo.find_do_resultado(uuid_item, resultado.id)
        if not p:
            raise RecursoNaoEncontradoError(f"Medicamento prescrito não encontrado: {uuid_item}")
        self.prescricao_repo.delete(p.id)

    # ------------------------------------------------------------------
    # Ponto único de criação (médico e IA passam por aqui)
    # ------------------------------------------------------------------
    def incluir(self, resultado, item: MedicamentoPrescritoIn, origem: str,
                id_output_origem: int | None = None, commit: bool = True):
        """origem e id_output_origem são decididos por quem chama, nunca pelo body."""
        from src.models.catalogos import CatalogoMedicamentos

        if not db.session.get(CatalogoMedicamentos, item.id_catalogo):
            raise RecursoNaoEncontradoError(f"Medicamento não encontrado no catálogo: {item.id_catalogo}")

        p = Prescricao(
            id_resultado_prescricao=resultado.id,
            origem_sugestao=origem,
            id_output_origem=id_output_origem,
            **item.model_dump(),  # só campos clínicos (extra="forbid" no schema)
        )
        return self.prescricao_repo.save(p, commit=commit)

    # --- D4: Medicamentos mais prescritos por classe ---
    def top_por_classe(self, id_empresa: int, dias: int = 30, limite: int = 10):
        return self.prescricao_repo.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)

    def top_principios_ativos_por_classe(self, id_empresa: int, classe: str, dias: int = 30, limite: int = 10):
        return self.prescricao_repo.top_principios_ativos_por_classe(
            id_empresa=id_empresa, classe=classe, dias=dias, limite=limite
        )