"""Interface que toda família de protocolo deve implementar.

O Service só conhece esta interface — nunca uma classe concreta.
"""
from abc import ABC, abstractmethod
from typing import Any
from ..schemas.schema_resultado import SchemaResultado


class CampoEsperado:
    def __init__(self, campo: str, texto: str, tipo_campo: str, opcoes: list[str] | None = None):
        self.campo = campo
        self.texto = texto
        self.tipo_campo = tipo_campo
        self.opcoes = opcoes


class ProtocoloStrategy(ABC):
    @abstractmethod
    def carregar_estrutura(self, dado_bruto: Any) -> Any:
        """Recebe o Model cru do Repository, devolve a estrutura validada pelo schema_x da família."""

    @abstractmethod
    def campos_esperados(self, estrutura: Any) -> list[CampoEsperado]:
        """Achata a estrutura em campos que o front sabe renderizar (numero/enum/booleano)."""

    @abstractmethod
    def validar_respostas(self, estrutura: Any, respostas: dict) -> dict:
        """Cruza respostas do front contra os campos declarados. Chave desconhecida -> rejeita."""

    @abstractmethod
    def executar(self, estrutura: Any, dados_validados: dict) -> SchemaResultado:
        """Função pura: estrutura + respostas -> SchemaResultado. Nunca acessa banco."""