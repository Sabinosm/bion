"""Este arquivo define o contrato de destino do registro operacional de chamadas à LLM."""
from typing import Protocol

from ...domain.schemas.auditoria import RegistroAuditoriaLLM


class AuditSink(Protocol):
    def registrar(self, registro: RegistroAuditoriaLLM) -> None:
        ...
