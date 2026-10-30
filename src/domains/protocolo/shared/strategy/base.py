"""base.py

Interface que toda família de protocolo implementa. O orquestrador de
execução conhece apenas esta abstração, nunca uma família concreta, o que
permite adicionar novas famílias sem alterar o fluxo genérico.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from ..schemas.schema_resultado import SchemaResultado


@dataclass
class CampoEsperado:
    """Campo que o front sabe renderizar.

    Contrato único para todas as famílias: `tipo_campo` é "numero", "enum" ou
    "booleano", e `opcoes` (só para "enum") é uma lista de {"valor", "rotulo"}.
    """
    campo: str
    texto: str
    tipo_campo: str
    opcoes: list[dict[str, str]] | None = None


class ProtocoloStrategy(ABC):

    # Valor de `ProtocoloCatalogo.tipo_protocolo` que esta família atende.
    TIPO_PROTOCOLO: ClassVar[str]

    @abstractmethod
    def carregar_estrutura(self, dado_bruto: Any) -> Any:
        """Converte o dado cru vindo do repository na estrutura validada da família."""

    @abstractmethod
    def campos_esperados(self, estrutura: Any) -> list[CampoEsperado]:
        """Achata a estrutura nos campos que o front precisa preencher."""

    @abstractmethod
    def validar_respostas(self, estrutura: Any, respostas: dict) -> dict:
        """Valida as respostas do front contra os campos declarados.

        Raises:
            ValueError: se houver campo desconhecido ou valor inválido.
        """

    @abstractmethod
    def executar(self, estrutura: Any, dados_validados: dict) -> SchemaResultado:
        """Calcula o resultado. Função pura: nunca acessa o banco."""
