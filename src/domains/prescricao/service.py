"""Regras de negócio do registro de resultado clínico de um Atendimento."""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import ResultadoPrescricaoRepository, PrescricaoRepository, PrescricaoExameRepository
from src.domains.atendimento.repository import AtendimentoRepository

CAMPOS_OBRIGATORIOS_RESULTADO = (
    "codigo_cid10_principal", "descricao_cid10_principal", "certeza_diagnostica",
)


class PrescricaoService:
    """
    Casos de uso de registro do resultado clínico de um atendimento
    (diagnóstico + condutas): ResultadoPrescricao, Prescricao
    (medicamentos) e PrescricaoExame.
    """

    def __init__(self):
        self.resultado_repo = ResultadoPrescricaoRepository()
        self.prescricao_repo = PrescricaoRepository()
        self.exame_repo = PrescricaoExameRepository()
        self.atendimento_repo = AtendimentoRepository()

    def registrar_resultado(self, uuid_atendimento: str, dados: dict, id_usuario: int):
        """
        Registra o diagnóstico (CID-10) e desfecho de um Atendimento.

        Raises:
            RecursoNaoEncontradoError: se o Atendimento não existir.
            DadosInvalidosError: se faltar algum campo obrigatório.
        """
        from src.models.clinico import ResultadoPrescricao
        atendimento = self.atendimento_repo.find_by_uuid(uuid_atendimento)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")

        faltando = [c for c in CAMPOS_OBRIGATORIOS_RESULTADO if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        resultado = ResultadoPrescricao(
            id_atendimento=atendimento.id,
            id_output=dados.get("id_output"),
            codigo_cid10_principal=dados["codigo_cid10_principal"],
            descricao_cid10_principal=dados["descricao_cid10_principal"],
            certeza_diagnostica=dados["certeza_diagnostica"],
            tipo_prescricao=dados.get("tipo_prescricao"),
            consistente_com_classificacao=dados.get("consistente_com_classificacao"),
            formulado_por=id_usuario,
            data_hora_formulacao=datetime.now(timezone.utc),
        )
        return self.resultado_repo.save(resultado)

    def adicionar_medicamento(self, uuid_resultado: str, dados: dict):
        """
        Adiciona um medicamento prescrito a um ResultadoPrescricao.

        Raises:
            RecursoNaoEncontradoError: se o ResultadoPrescricao não existir.
        """
        from src.models.clinico import Prescricao
        resultado = self.resultado_repo.find_by_uuid(uuid_resultado)
        if not resultado:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")

        p = Prescricao(
            id_resultado_prescricao=resultado.id,
            id_catalogo=dados.get("id_catalogo"),
            dose=dados.get("dose"),
            frequencia=dados.get("frequencia"),
            duracao=dados.get("duracao"),
            orientacoes=dados.get("orientacoes"),
        )
        return self.prescricao_repo.save(p)

    def adicionar_exame(self, uuid_resultado: str, dados: dict):
        """
        Adiciona um exame prescrito a um ResultadoPrescricao.

        Raises:
            RecursoNaoEncontradoError: se o ResultadoPrescricao não existir.
        """
        from src.models.clinico import PrescricaoExame
        resultado = self.resultado_repo.find_by_uuid(uuid_resultado)
        if not resultado:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")

        pe = PrescricaoExame(
            id_resultado=resultado.id,
            id_exame=dados.get("id_exame"),
            urgencia=dados.get("urgencia", "rotina"),
            justificativa=dados.get("justificativa"),
            origem_sugestao=dados.get("origem_sugestao", "medico"),
            id_output_origem=dados.get("id_output_origem"),
        )
        return self.exame_repo.save(pe)

    def buscar_resultado_por_uuid(self, uuid: str):
        """Retorna um ResultadoPrescricao pelo UUID ou lança RecursoNaoEncontradoError."""
        r = self.resultado_repo.find_by_uuid(uuid)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid}")
        return r
