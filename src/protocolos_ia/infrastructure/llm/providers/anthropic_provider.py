"""Este arquivo implementa o provedor da API Messages da Anthropic. Traduz falhas HTTP em erros classificados, sem expor corpo, cabeçalhos ou chave."""
from __future__ import annotations

from typing import Callable, Optional

import requests

from ....domain.schemas.requests import LLMRequest
from ..config import ConfiguracaoLLM
from ..exceptions import ErroPermanenteProvedor, ErroTransitorioProvedor, RespostaLLMInvalidaError
from ..raw_response import RawLLMResponse

TIMEOUT_CONEXAO_SEGUNDOS = 5.0
RETRY_AFTER_MAXIMO = 30.0


def _retry_after(resposta) -> Optional[float]:
    bruto = resposta.headers.get("retry-after") if getattr(resposta, "headers", None) else None
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        return None
    return min(max(valor, 0.0), RETRY_AFTER_MAXIMO)


class AnthropicProvider:
    nome_provedor = "anthropic"
    simulado = False

    def __init__(self, config: ConfiguracaoLLM, http_post: Optional[Callable] = None):
        self._config = config
        self._post = http_post or requests.post

    @property
    def nome_modelo(self) -> str:
        return self._config.modelo

    def executar(self, request: LLMRequest) -> RawLLMResponse:
        cfg = self._config
        try:
            resposta = self._post(
                cfg.url_base,
                headers={
                    "x-api-key": cfg.api_key,
                    "anthropic-version": cfg.anthropic_version,
                    "content-type": "application/json",
                },
                json={
                    "model": cfg.modelo,
                    "max_tokens": cfg.max_tokens,
                    "temperature": cfg.temperatura,
                    "system": request.system,
                    "messages": [{"role": "user", "content": request.prompt}],
                },
                timeout=(TIMEOUT_CONEXAO_SEGUNDOS, cfg.timeout_segundos),
            )
        except requests.exceptions.Timeout:
            raise ErroTransitorioProvedor("timeout") from None
        except requests.exceptions.ConnectionError:
            raise ErroTransitorioProvedor("erro_de_conexao") from None
        except requests.exceptions.RequestException:
            raise ErroPermanenteProvedor(detalhes="requisicao_invalida") from None

        status = resposta.status_code
        if status == 429 or status >= 500:
            raise ErroTransitorioProvedor(f"http_{status}", _retry_after(resposta))
        if status >= 400:
            raise ErroPermanenteProvedor(detalhes=f"http_{status}")

        try:
            dados = resposta.json()
        except ValueError:
            raise ErroPermanenteProvedor(detalhes="corpo_nao_json") from None
        if not isinstance(dados, dict):
            raise RespostaLLMInvalidaError("corpo_inesperado")

        blocos = dados.get("content")
        textos = [
            b["text"]
            for b in (blocos if isinstance(blocos, list) else [])
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        ]
        if not textos:
            raise RespostaLLMInvalidaError("sem_bloco_de_texto")

        uso = dados.get("usage") if isinstance(dados.get("usage"), dict) else {}
        entrada, saida = uso.get("input_tokens", 0), uso.get("output_tokens", 0)
        return RawLLMResponse(
            texto="".join(textos),
            modelo=cfg.modelo,
            tokens_entrada=entrada if isinstance(entrada, int) and not isinstance(entrada, bool) else 0,
            tokens_saida=saida if isinstance(saida, int) and not isinstance(saida, bool) else 0,
            motivo_parada=dados.get("stop_reason") if isinstance(dados.get("stop_reason"), str) else None,
        )
