"""Contrato de domínio para obtenção de prompts versionados. A implementação pertence à infraestrutura."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PromptMontado:
    """Prompt separado em regras do sistema e mensagem do usuário que carrega os dados clínicos."""

    sistema: str
    usuario: str


class PromptSource(Protocol):
    def montar(self, tipo_analise: str, versao: str, contexto_json: str) -> PromptMontado:
        ...
