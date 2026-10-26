"""Este arquivo grava o registro operacional de cada chamada à LLM no log estruturado. Contém só metadados técnicos, nunca dados clínicos."""
from __future__ import annotations

import logging

from ...domain.schemas.auditoria import RegistroAuditoriaLLM

logger = logging.getLogger("bion.ia.auditoria")


class LlmAuditService:
    def registrar(self, registro: RegistroAuditoriaLLM) -> None:
        """Esta função emite uma linha de log com os campos do registro como atributos estruturados."""
        logger.info("chamada_llm", extra={"auditoria_llm": registro.model_dump(mode="json")})
