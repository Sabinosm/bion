"""cost_calculator.py

Estima o custo em USD de uma chamada a partir dos tokens, para observabilidade; não é cobrança. A tabela de preços
por modelo vem do código e pode ser ampliada ou sobrescrita pela variável LLM_PRECOS_POR_MILHAO (JSON com o nome
do modelo e o par entrada/saída em USD por milhão de tokens). Modelo fora da tabela usa um preço de reserva e é
marcado como preço desconhecido, para que ninguém leia a estimativa como valor real.
"""
from __future__ import annotations

import json
from typing import Mapping, Optional

from .exceptions import ConfiguracaoLLMInvalidaError

# Preços em USD por milhão de tokens (entrada, saída). Revisar quando a tabela do provedor mudar.
PRECOS_POR_MILHAO = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
PRECO_DESCONHECIDO = (3.0, 15.0)


class CostCalculator:
    def __init__(self, precos: Optional[Mapping[str, tuple[float, float]]] = None):
        self._precos = dict(PRECOS_POR_MILHAO if precos is None else precos)

    @classmethod
    def do_ambiente(cls, env: Mapping[str, str]) -> "CostCalculator":
        """Tabela do código somada ao JSON de LLM_PRECOS_POR_MILHAO, que prevalece em caso de conflito."""
        bruto = env.get("LLM_PRECOS_POR_MILHAO")
        precos = dict(PRECOS_POR_MILHAO)
        if bruto:
            try:
                dados = json.loads(bruto)
                for modelo, par in dados.items():
                    entrada, saida = par
                    if not isinstance(modelo, str) or not modelo or isinstance(entrada, bool) or isinstance(saida, bool) \
                            or not isinstance(entrada, (int, float)) or not isinstance(saida, (int, float)) \
                            or entrada < 0 or saida < 0:
                        raise ValueError
                    precos[modelo] = (float(entrada), float(saida))
            except (ValueError, TypeError, AttributeError):
                raise ConfiguracaoLLMInvalidaError("LLM_PRECOS_POR_MILHAO", "JSON inválido ou preços negativos") from None
        return cls(precos)

    def preco_conhecido(self, modelo: str) -> bool:
        return modelo.startswith("mock") or modelo in self._precos

    def estimar(self, modelo: str, tokens_entrada: int, tokens_saida: int) -> float:
        """Custo estimado. Modelo fora da tabela usa o preço de reserva e mock custa zero."""
        if modelo.startswith("mock"):
            return 0.0
        preco_in, preco_out = self._precos.get(modelo, PRECO_DESCONHECIDO)
        return round((tokens_entrada * preco_in + tokens_saida * preco_out) / 1_000_000, 6)
