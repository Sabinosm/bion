"""Este arquivo converte o texto bruto da LLM em RespostaLLM validada. Falhas nunca carregam o conteúdo recebido."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ...domain.schemas.responses import RespostaLLM
from .exceptions import RespostaLLMInvalidaError

TAMANHO_MAXIMO = 100_000
_CERCA = re.compile(r"^```(?:json)?[ \t]*\r?\n(.*)\r?\n```[ \t]*$", re.DOTALL | re.IGNORECASE)


def _rejeitar_constante(_nome: str):
    raise ValueError("constante numérica não permitida")


class ResponseParser:
    def parsear(self, texto: str) -> RespostaLLM:
        """Esta função aceita um objeto JSON, opcionalmente dentro de uma cerca markdown, e o valida contra RespostaLLM."""
        if not isinstance(texto, str) or not texto.strip():
            raise RespostaLLMInvalidaError("resposta_vazia")
        if len(texto) > TAMANHO_MAXIMO:
            raise RespostaLLMInvalidaError("resposta_grande_demais")
        limpo = texto.strip()
        cerca = _CERCA.match(limpo)
        if cerca:
            limpo = cerca.group(1).strip()
        try:
            dados = json.loads(limpo, parse_constant=_rejeitar_constante)
        except (ValueError, RecursionError):
            raise RespostaLLMInvalidaError("json_malformado") from None
        if not isinstance(dados, dict):
            raise RespostaLLMInvalidaError("json_nao_e_objeto")
        try:
            return RespostaLLM.model_validate(dados)
        except ValidationError as exc:
            campos = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
            raise RespostaLLMInvalidaError(f"schema_invalido: {', '.join(campos)[:200]}") from None
