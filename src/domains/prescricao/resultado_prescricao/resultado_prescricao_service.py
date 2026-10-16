from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, PermissaoNegadaError, ConflictoError
from .resultado_prescricao_repository import ResultadoPrescricaoRepository
from ..schema_prescricoes import ResultadoPrescricaoIn
from ..prescricao_validacao_service import PrescricaoValidacaoService


class ResultadoPrescricaoService:
    def __init__(self):
        self.resultado_repo = ResultadoPrescricaoRepository()
        self.validacao_svc = PrescricaoValidacaoService()

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
            raise PermissaoNegadaError("Apenas o profissional do atendimento pode registrar o resultado.")

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
            raise PermissaoNegadaError("Apenas o médico responsável pode alterar esta prescrição.")
        if r.status != "rascunho":
            raise ConflictoError("Prescrição já confirmada; não pode mais ser alterada.")
        return r

    def confirmar(self, uuid_resultado: str, id_empresa: int, id_usuario: int,
                  reconhecer_alertas: bool = False):
        """O médico passa a responder pela prescrição (rascunho -> confirmado).

        Se houver alertas de interação, a confirmação exige reconhecimento explícito
        (reconhecer_alertas=True). Retorna (resultado, verificacao)."""
        r = self.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        if r.tipo_prescricao == "farmacologica" and not r.prescricoes:
            raise ConflictoError("Prescrição farmacológica exige ao menos um medicamento.")

        verificacao = self.validacao_svc.verificar_interacoes(self._ids_medicamentos(r))
        if verificacao["alertas"] and not reconhecer_alertas:
            raise ConflictoError(
                f"{len(verificacao['alertas'])} alerta(s) de interação medicamentosa. "
                "Revise (GET /<uuid_resultado>/alertas) e confirme com reconhecer_alertas=true."
            )

        r.status = "confirmado"
        r.confirmado_em = datetime.now(timezone.utc)
        return self.resultado_repo.save(r), verificacao

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def buscar_resultado_por_uuid(self, uuid_resultado: str, id_empresa: int):
        r = self.resultado_repo.find_by_uuid_da_empresa(uuid_resultado, id_empresa)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")
        return r

    def verificar_alertas(self, uuid_resultado: str, id_empresa: int) -> dict:
        """Interações do conjunto atual de medicamentos do resultado."""
        r = self.buscar_resultado_por_uuid(uuid_resultado, id_empresa)
        return self.validacao_svc.verificar_interacoes(self._ids_medicamentos(r))

    @staticmethod
    def _ids_medicamentos(resultado) -> set[int]:
        return {p.id_catalogo for p in resultado.prescricoes if p.id_catalogo}

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