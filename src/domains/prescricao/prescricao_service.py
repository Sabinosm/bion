"""Regras de negócio do registro de resultado clínico de um Atendimento."""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .prescricao_repository import  PrescricaoRepository
from .prescricao_exame_repository import PrescricaoExameRepository
from src.domains.atendimento.repository import AtendimentoRepository
from .resultado_prescricao_repository import ResultadoPrescricaoRepository

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
        self.repo = ResultadoPrescricaoRepository()
        self.prescricao_repo = PrescricaoRepository()
        self.exame_repo = PrescricaoExameRepository()
        self.atendimento_repo = AtendimentoRepository()

    def find_by_uuid(self, uuid):
        return self.repo.find_by_uuid(uuid)
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
        return self.repo.save(resultado)

    def adicionar_medicamento(self, uuid_resultado: str, dados: dict):
        """
        Adiciona um medicamento prescrito a um ResultadoPrescricao.

        Raises:
            RecursoNaoEncontradoError: se o ResultadoPrescricao não existir.
        """
        from src.models.clinico import Prescricao
        resultado = self.repo.find_by_uuid(uuid_resultado)
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


    def buscar_resultado_por_uuid(self, uuid: str):
        """Retorna um ResultadoPrescricao pelo UUID ou lança RecursoNaoEncontradoError."""
        r = self.repo.find_by_uuid(uuid)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid}")
        return r
    
    def top_cid_por_regiao(self, id_empresa: int, dias: int = 14, limite: int = 10):
        return self.repo.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)
 
    # --- D4: Medicamentos mais prescritos por classe ---
    def top_por_classe(self, id_empresa: int, dias: int = 30, limite: int = 10):
        return self.repo.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)
 
    def top_principios_ativos_por_classe(self, id_empresa: int, classe: str, dias: int = 30, limite: int = 10):
        return self.repo.top_principios_ativos_por_classe(
            id_empresa=id_empresa, classe=classe, dias=dias, limite=limite
        )