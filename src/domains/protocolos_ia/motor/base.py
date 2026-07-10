"""Contratos do motor de protocolos determinísticos (padrão Strategy + Factory)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InputTriagem:
    """Entrada de um protocolo de triagem (ex: MTS, NEWS2)."""
    input_json: dict = field(default_factory=dict)
    sinais_vitais: list = field(default_factory=list)
    queixa_principal: Optional[str] = None


@dataclass
class ResultadoTriagem:
    """
    Resultado de um protocolo de triagem.

    Campos suficientemente amplos para acomodar tanto triagem por cor
    (ex: MTS) quanto por score numérico (ex: NEWS2), com os campos
    específicos de cada tipo sendo opcionais. Evita criar uma hierarquia
    de subclasses para apenas dois casos, mantendo compatibilidade caso
    um terceiro protocolo de triagem por cor ou por score seja adicionado.
    """
    # Campos de protocolos de cor (ex.: MTS)
    cor_mts: Optional[str] = None
    tempo_max_espera: Optional[int] = None
    discriminadores_avaliados: list = field(default_factory=list)
    discriminante_determinante: Optional[str] = None
    # Campos de protocolos de score (ex.: NEWS2)
    nivel_risco_news2: Optional[str] = None
    score_news2: Optional[int] = None
    subscores_news2: dict = field(default_factory=dict)
    # Comum a qualquer protocolo de triagem
    alertas: list = field(default_factory=list)


@dataclass
class InputConsulta:
    """Entrada de um protocolo aplicado durante a consulta/avaliação médica."""
    input_json: dict = field(default_factory=dict)
    sinais_vitais: list = field(default_factory=list)


@dataclass
class ResultadoConsulta:
    """Resultado de um protocolo aplicado durante a consulta/avaliação médica."""
    alertas: list = field(default_factory=list)
    indice_confianca: float = 0.0


class IProtocoloTriagem(ABC):
    """Contrato (Strategy) para protocolos executados na etapa de triagem."""

    @abstractmethod
    def executar(self, inp: InputTriagem) -> ResultadoTriagem:
        """Executa o protocolo sobre o input de triagem e retorna o resultado."""
        ...

    @abstractmethod
    def validar_input(self, i: InputTriagem) -> bool:
        """Retorna True se o input tem dados suficientes para executar o protocolo."""
        ...

    @abstractmethod
    def get_nome(self) -> str:
        """Retorna o nome de exibição do protocolo."""
        ...

    @abstractmethod
    def get_versao(self) -> str:
        """Retorna a versão/edição do protocolo implementada."""
        ...


class IProtocoloConsulta(ABC):
    """Contrato (Strategy) para protocolos executados na etapa de consulta/avaliação médica."""

    @abstractmethod
    def executar(self, inp: InputConsulta) -> ResultadoConsulta:
        """Executa o protocolo sobre o input de consulta e retorna o resultado."""
        ...

    @abstractmethod
    def validar_input(self, i: InputConsulta) -> bool:
        """Retorna True se o input tem dados suficientes para executar o protocolo."""
        ...

    @abstractmethod
    def get_nome(self) -> str:
        """Retorna o nome de exibição do protocolo."""
        ...

    @abstractmethod
    def get_versao(self) -> str:
        """Retorna a versão/edição do protocolo implementada."""
        ...
