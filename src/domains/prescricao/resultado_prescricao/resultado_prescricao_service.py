from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, AcessoNegadoError, ConflitoError
from .resultado_prescricao_repository import ResultadoPrescricaoRepository
from ..schema_prescricoes import ResultadoPrescricaoIn


class ResultadoPrescricaoService:
    def __init__(self):
        self.resultado_repo = ResultadoPrescricaoRepository()

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def registrar_resultado(self, uuid_atendimento: str, dados: ResultadoPrescricaoIn,
                            id_usuario: int, id_output: int | None = None, commit: bool = True):
        """Cria um ResultadoPrescricao em RASCUNHO, ligado ao médico da sessão.

        id_output só é informado pelo fluxo da IA (nunca vem do body).
        """
        from src.models.clinico import Atendimento, ResultadoPrescricao

        atendimento = Atendimento.query.filter_by(uuid=uuid_atendimento).first()
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        if atendimento.realizado_por != id_usuario:
            raise AcessoNegadoError("Apenas o profissional do atendimento pode registrar o resultado.")

        r = ResultadoPrescricao(
            id_atendimento=atendimento.id,
            id_output=id_output,
            formulado_por=id_usuario,
            status="rascunho",
            **dados.model_dump(),
        )
        return self.resultado_repo.save(r, commit=commit)

    def obter_rascunho_editavel(self, uuid_resultado: str, id_empresa: int, id_usuario: int):
        """Resultado da empresa, ainda em rascunho e do próprio formulador.
        Usado antes de qualquer alteração de itens (adicionar/remover)."""
        r = self.resultado_repo.find_by_uuid_da_empresa(uuid_resultado, id_empresa)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")
        if r.formulado_por != id_usuario:
            raise AcessoNegadoError("Apenas o médico responsável pode alterar esta prescrição.")
        if r.status != "rascunho":
            raise ConflitoError("Prescrição já confirmada; não pode mais ser alterada.")
        return r

    def confirmar(self, uuid_resultado: str, id_empresa: int, id_usuario: int):
        """O médico passa a responder pela prescrição (rascunho -> confirmado)."""
        r = self.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        if r.tipo_prescricao == "farmacologica" and not r.prescricoes:
            raise ConflitoError("Prescrição farmacológica exige ao menos um medicamento.")
        r.status = "confirmado"
        r.confirmado_em = datetime.now(timezone.utc)
        return self.resultado_repo.save(r)

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def buscar_resultado_por_uuid(self, uuid_resultado: str, id_empresa: int):
        r = self.resultado_repo.find_by_uuid_da_empresa(uuid_resultado, id_empresa)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")
        return r

    # --- C1: Doenças mais comuns por região ---
    def top_cid_por_regiao(self, id_empresa: int, dias: int = 14, limite: int = 10):
        return self.resultado_repo.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)

    # --- C3 (bônus): base para incidência por 100 mil ---
    def total_casos_por_regiao(self, id_empresa: int, dias: int = 14):
        return self.resultado_repo.total_casos_por_regiao(id_empresa=id_empresa, dias=dias)

    # --- C2: Evolução temporal de um CID específico ---
    def evolucao_cid(self, id_empresa: int, codigo_cid10: str, dias: int = 30):
        return self.resultado_repo.evolucao_cid(id_empresa=id_empresa, codigo_cid10=codigo_cid10, dias=dias)

    # --- C2 (comparação): evolução de 1 CID, com janela explícita ---
    def evolucao_cid_periodo(self, id_empresa: int, codigo_cid10: str, data_inicio, data_fim):
        return self.resultado_repo.evolucao_cid_periodo(
            id_empresa=id_empresa, codigo_cid10=codigo_cid10, data_inicio=data_inicio, data_fim=data_fim
        )