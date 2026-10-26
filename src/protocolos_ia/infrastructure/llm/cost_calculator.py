"""Este arquivo estima o custo em USD de uma chamada a partir dos tokens. O valor é uma estimativa para observabilidade."""
from __future__ import annotations

# Preços em USD por milhão de tokens (entrada, saída). Revisar quando a tabela do provedor mudar.
PRECOS_POR_MILHAO = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
PRECO_DESCONHECIDO = (3.0, 15.0)


class CostCalculator:
    def estimar(self, modelo: str, tokens_entrada: int, tokens_saida: int) -> float:
        """Esta função devolve o custo estimado. Modelo fora da tabela usa o preço padrão e mock custa zero."""
        if modelo.startswith("mock"):
            return 0.0
        preco_in, preco_out = PRECOS_POR_MILHAO.get(modelo, PRECO_DESCONHECIDO)
        return round((tokens_entrada * preco_in + tokens_saida * preco_out) / 1_000_000, 6)
