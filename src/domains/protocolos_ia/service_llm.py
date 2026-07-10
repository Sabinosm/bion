"""Regras de negócio da análise clínica via IA generativa (LLM), complementar aos protocolos determinísticos."""

from .repository import OutputBionRepository
from .motor.ia_base import ContextoClinico
from .motor.llm_motor import LlmMotor


class OutputBionLlmService:
    """
    Casos de uso de análise clínica via IA generativa (Claude), usada
    tipicamente na avaliação médica, após a triagem, para sugerir
    diagnósticos/condutas com base no contexto clínico completo do
    atendimento. Requer LLM_API_KEY configurada (.env); a decisão final
    permanece sempre do profissional de saúde.
    """

    def __init__(self):
        self.repo = OutputBionRepository()

    def analisar_com_llm(self, contexto: ContextoClinico, id_input_protocolo: int = None):
        """
        Executa a análise via LlmMotor e persiste o resultado como OutputBion.

        Args:
            contexto: dados clínicos consolidados (sinais vitais, alergias,
                doenças, medicamentos em uso, resultado da triagem).
            id_input_protocolo: ID do InputProtocolo de origem, se houver.
        """
        motor = LlmMotor()
        resultado_json = motor.analisar(contexto)

        from src.models.protocolos import OutputBion
        output = OutputBion(
            id_input=id_input_protocolo,
            output_ia_json=resultado_json,
            versao_modelo_ia=f"{motor.get_nome_modelo()}-{motor.get_versao()}",
            indice_completude=None,
            indice_confianca=None,
        )
        return self.repo.save(output)
