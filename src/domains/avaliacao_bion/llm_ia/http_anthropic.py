"""http_anthropic.py

Apoio compartilhado dos clientes HTTP da API Messages da Anthropic: limites de tempo, leitura do cabecalho Retry-After e extracao dos tokens usados. Centraliza o que era duplicado entre o provedor de analise e o cliente de avaliacao.
"""
from typing import Optional

TIMEOUT_CONEXAO_SEGUNDOS = 5.0
RETRY_AFTER_MAXIMO = 30.0


def retry_after(resposta) -> Optional[float]:
    """Segundos pedidos pelo provedor no cabeçalho Retry-After, limitados a RETRY_AFTER_MAXIMO. None se ausente ou inválido."""
    headers = getattr(resposta, "headers", None) or {}
    try:
        valor = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None
    return min(max(valor, 0.0), RETRY_AFTER_MAXIMO)


def _inteiro(valor) -> int:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def tokens_de_uso(dados: dict) -> tuple[int, int]:
    """(tokens_entrada, tokens_saida) do campo usage da resposta; valores ausentes ou inválidos contam como 0."""
    uso = dados.get("usage") if isinstance(dados.get("usage"), dict) else {}
    return _inteiro(uso.get("input_tokens", 0)), _inteiro(uso.get("output_tokens", 0))
