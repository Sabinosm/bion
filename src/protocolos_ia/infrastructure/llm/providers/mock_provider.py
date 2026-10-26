"""Este arquivo implementa um provedor simulado e determinístico para desenvolvimento e testes. Não faz chamadas de rede e marca toda resposta como simulada."""
from __future__ import annotations

import json
from typing import List, Optional

from ....domain.schemas.requests import LLMRequest
from ....domain.schemas.responses import DISCLAIMER_CLINICO
from ..raw_response import RawLLMResponse

RESPOSTA_PADRAO = {
    "resumo_clinico": (
        "[SIMULADO] Resposta de teste gerada sem modelo de linguagem real. "
        "Não utilizar em decisão clínica. Conteúdo fixo para validação de integração."
    ),
    "hipoteses_diagnosticas": [
        {
            "descricao": "Hipótese simulada de teste",
            "codigo_cid10": None,
            "probabilidade": "baixa",
            "dados_que_suportam": [],
            "dados_que_contradizem": [],
        }
    ],
    "alertas": ["Resposta SIMULADA (provedor mock). Não utilizar em decisão clínica."],
    "exames_sugeridos": [],
    "medicamentos_sugeridos": [],
    "explicacao_divergencia": None,
    "disclaimer_clinico": DISCLAIMER_CLINICO,
}


class MockProvider:
    nome_provedor = "mock"
    nome_modelo = "mock-model-v1"
    simulado = True

    def __init__(
        self,
        resposta: Optional[dict] = None,
        texto_bruto: Optional[str] = None,
        erro: Optional[Exception] = None,
    ):
        self._resposta = resposta if resposta is not None else RESPOSTA_PADRAO
        self._texto_bruto = texto_bruto
        self._erro = erro
        self.chamadas: List[LLMRequest] = []

    def executar(self, request: LLMRequest) -> RawLLMResponse:
        self.chamadas.append(request)
        if self._erro is not None:
            raise self._erro
        texto = self._texto_bruto if self._texto_bruto is not None else json.dumps(self._resposta, ensure_ascii=False)
        return RawLLMResponse(
            texto=texto,
            modelo=self.nome_modelo,
            tokens_entrada=max(1, len(request.prompt) // 4),
            tokens_saida=max(1, len(texto) // 4),
            motivo_parada="end_turn",
        )
