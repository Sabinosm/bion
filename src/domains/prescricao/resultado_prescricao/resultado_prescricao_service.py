from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, PermissaoNegadaError, ConflictoError
from src.domains.atendimento.repository import AtendimentoRepository
from .resultado_prescricao_repository import ResultadoPrescricaoRepository
from ..schema_prescricoes import ResultadoPrescricaoIn, ResultadoPrescricaoPatch
from ..prescricao_validacao_service import PrescricaoValidacaoService

# Origem do RESULTADO (não confundir com a origem de cada item): quem responde pelo conteúdo agora.
ORIGEM_IA = "bion_ia"
ORIGEM_MEDICO = "medico"


class ResultadoPrescricaoService:
    """Regras do ResultadoPrescricao (diagnóstico + categoria). Sem step-up: a prescrição acontece
    durante o atendimento e o médico não deve ser interrompido; a rastreabilidade vem do log de
    acesso (quem, quando, o quê) e do próprio registro (origem, descarte).

    Invariantes:
      - só o médico dono do atendimento escreve, e só com o atendimento EM ANDAMENTO
        (descartar um rascunho antigo é a única escrita permitida fora de 'em-andamento');
      - no máximo um rascunho por atendimento para o fluxo do médico; a IA só coexiste com
        rascunhos da própria IA (trocados logo depois) e nunca com rascunho do médico;
      - qualquer alteração do médico (diagnóstico, item, adição, remoção) passa a origem do
        resultado para 'medico' e a IA deixa de poder trocá-lo.
    """

    def __init__(self):
        self.resultado_repo = ResultadoPrescricaoRepository()
        self.validacao_svc = PrescricaoValidacaoService()
        self.atendimento_repo = AtendimentoRepository()

    # ------------------------------------------------------------------
    # Apoio
    # ------------------------------------------------------------------
    def _atendimento_do_medico(self, uuid_atendimento: str, id_empresa: int, id_usuario: int):
        """404 igual para 'não existe' e 'outra empresa'; 403 se não é o profissional do atendimento."""
        atendimento = self.atendimento_repo.find_by_uuid(uuid_atendimento, id_empresa)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        if atendimento.realizado_por != id_usuario:
            raise PermissaoNegadaError("Apenas o profissional do atendimento pode usar a prescrição deste atendimento.")
        return atendimento

    @staticmethod
    def _exigir_em_andamento(atendimento) -> None:
        if atendimento.status != "em-andamento":
            raise ConflictoError(
                f"Atendimento {atendimento.status}: a prescrição só pode ser alterada com o atendimento em andamento."
            )

    @staticmethod
    def marcar_editado(resultado) -> None:
        """O médico mexeu: o resultado deixa de ser 'da IA'. Só muda o atributo; quem chama commita
        (assim a alteração e a troca de origem saem na mesma transação)."""
        resultado.origem_sugestao = ORIGEM_MEDICO

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def registrar_resultado(self, uuid_atendimento: str, dados: ResultadoPrescricaoIn,
                            id_empresa: int, id_usuario: int, id_output: int | None = None,
                            commit: bool = True):
        """Cria um ResultadoPrescricao em RASCUNHO, ligado ao médico da sessão.

        id_output só é informado pelo fluxo da IA (nunca vem do body): ele define a origem 'bion_ia'.

        Raises: 404 (atendimento inexistente/de outra empresa), 403 (não é o dono),
        409 (atendimento fora de 'em-andamento'; já há rascunho; ou, no fluxo da IA, há rascunho do médico).
        """
        from src.models.clinico import ResultadoPrescricao

        atendimento = self._atendimento_do_medico(uuid_atendimento, id_empresa, id_usuario)
        self._exigir_em_andamento(atendimento)

        rascunhos = [r for r in atendimento.resultados_prescricao if r.status == "rascunho"]
        if id_output is None and rascunhos:
            raise ConflictoError(
                "Já existe uma prescrição em rascunho neste atendimento: edite-a, confirme-a ou descarte-a "
                "antes de criar outra."
            )
        if id_output is not None and any(r.origem_sugestao != ORIGEM_IA for r in rascunhos):
            raise ConflictoError(
                "Há uma prescrição em rascunho do médico neste atendimento: confirme-a ou descarte-a "
                "antes de receber a proposta da IA."
            )

        r = ResultadoPrescricao(
            id_atendimento=atendimento.id,
            id_output=id_output,
            formulado_por=id_usuario,
            status="rascunho",
            origem_sugestao=ORIGEM_IA if id_output is not None else ORIGEM_MEDICO,
            **dados.model_dump(),
        )
        return self.resultado_repo.save(r, commit=commit)

    def obter_rascunho_editavel(self, uuid_resultado: str, id_empresa: int, id_usuario: int):
        """Resultado da empresa, ainda em rascunho, do próprio formulador e de atendimento em andamento.
        Usado antes de qualquer alteração (diagnóstico, itens) e na confirmação."""
        r = self.resultado_repo.find_by_uuid_da_empresa(uuid_resultado, id_empresa)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")
        if r.formulado_por != id_usuario:
            raise PermissaoNegadaError("Apenas o médico responsável pode alterar esta prescrição.")
        if r.status == "confirmado":
            raise ConflictoError("Prescrição já confirmada; não pode mais ser alterada.")
        if r.status == "descartado":
            raise ConflictoError("Prescrição descartada; não pode mais ser alterada.")
        self._exigir_em_andamento(r.atendimento)
        return r

    def atualizar_diagnostico(self, uuid_resultado: str, dados: ResultadoPrescricaoPatch,
                              id_empresa: int, id_usuario: int):
        """Altera só os campos enviados do diagnóstico. Se algo realmente mudou, a origem passa a 'medico'."""
        r = self.obter_rascunho_editavel(uuid_resultado, id_empresa, id_usuario)
        mudancas = {k: v for k, v in dados.model_dump(exclude_unset=True).items() if getattr(r, k) != v}
        if not mudancas:
            return r
        for campo, valor in mudancas.items():
            setattr(r, campo, valor)
        self.marcar_editado(r)
        return self.resultado_repo.save(r)

    def descartar(self, uuid_resultado: str, id_empresa: int, id_usuario: int, motivo: str | None = None):
        """Descarte LÓGICO do rascunho (nada é apagado). Vale mesmo com o atendimento já finalizado ou
        cancelado, para não deixar rascunho preso; confirmado não se descarta."""
        r = self.resultado_repo.find_by_uuid_da_empresa(uuid_resultado, id_empresa)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")
        if r.formulado_por != id_usuario:
            raise PermissaoNegadaError("Apenas o médico responsável pode descartar esta prescrição.")
        if r.status == "confirmado":
            raise ConflictoError("Prescrição já confirmada; não pode ser descartada.")
        if r.status == "descartado":
            raise ConflictoError("Prescrição já foi descartada.")
        r.status = "descartado"
        r.descartado_em = datetime.now(timezone.utc)
        r.descartado_por = id_usuario
        r.motivo_descarte = motivo
        return self.resultado_repo.save(r)

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
    def listar_do_atendimento(self, uuid_atendimento: str, id_empresa: int, id_usuario: int):
        """Resultados do atendimento (rascunho, confirmado e descartado), do mais antigo ao mais novo.
        Só o dono; vale em qualquer status do atendimento (histórico)."""
        atendimento = self._atendimento_do_medico(uuid_atendimento, id_empresa, id_usuario)
        return self.resultado_repo.find_do_atendimento(atendimento.id)

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