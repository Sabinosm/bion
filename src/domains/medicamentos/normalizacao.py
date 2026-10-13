"""Normalização de nomes de princípio ativo para cruzar fontes
diferentes (ANVISA usa 'CLORIDRATO DE X' em maiúsculas; Detecta
Interações usa nomes simples como 'Paracetamol')."""

import re
import unicodedata

_PREFIXOS_SAL = (
    "cloridrato de ", "sulfato de ", "maleato de ", "fosfato de ",
    "acetato de ", "succinato de ", "tartarato de ", "besilato de ",
)


def normalizar_nome(nome: str) -> str:
    """Minúsculas, sem acento, espaços colapsados, sem prefixo de sal.

    Não trata combinações ('A + B'): quem chama decide o que fazer com
    elas (o parser da ANVISA, por exemplo, pula esses itens).
    """
    s = unicodedata.normalize("NFKD", nome)
    s = s.encode("ascii", "ignore").decode("ascii").lower().strip()
    s = re.sub(r"\s+", " ", s)
    for prefixo in _PREFIXOS_SAL:
        if s.startswith(prefixo):
            return s[len(prefixo):]
    return s