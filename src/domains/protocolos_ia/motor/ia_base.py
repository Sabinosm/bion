"""
Contrato do motor de IA generativa (LLM), distinto do motor de protocolos
por Strategy (MTS/NEWS2/PP). Este motor recebe o contexto clínico completo
do atendimento e devolve sugestões de diagnóstico/conduta — sempre como
apoio à decisão, nunca substituindo o julgamento do profissional.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ContextoClinico:
    """Dados clínicos consolidados de um atendimento, usados como entrada para o motor de LLM."""
    paciente: Any = None
    sinais_vitais: List[Dict] = field(default_factory=list)
    alergias: List[Dict] = field(default_factory=list)
    doencas: List[Dict] = field(default_factory=list)
    medicamentos_em_uso: List[Dict] = field(default_factory=list)
    input_protocolo: Any = None
    resultado_triagem: Optional[Any] = None

    def serializar(self) -> Dict[str, Any]:
        """Converte o contexto clínico em um dict serializável para envio ao modelo de IA."""
        return {
            "paciente": {
                "sexo": getattr(self.paciente, "sexo_biologico", None),
                "nascimento": str(getattr(self.paciente, "data_nascimento", "")),
            },
            "sinais_vitais": self.sinais_vitais,
            "alergias": self.alergias,
            "doencas": self.doencas,
            "medicamentos": self.medicamentos_em_uso,
            "resultado_triagem": str(self.resultado_triagem) if self.resultado_triagem else None,
        }


class IMotorIA(ABC):
    """Contrato para motores de IA generativa usados como apoio à decisão clínica."""

    @abstractmethod
    def analisar(self, ctx: ContextoClinico) -> Dict[str, Any]:
        """Analisa o contexto clínico e retorna sugestões estruturadas (diagnósticos, condutas, alertas)."""
        ...

    @abstractmethod
    def get_nome_modelo(self) -> str:
        """Retorna o identificador do modelo de IA utilizado."""
        ...

    @abstractmethod
    def get_versao(self) -> str:
        """Retorna a versão do motor de IA."""
        ...
