"""Normalização de nomes de princípio ativo para cruzar fontes
diferentes (ANVISA usa 'CLORIDRATO DE X' em maiúsculas; Detecta
Interações usa nomes simples como 'Paracetamol')."""

import re
import unicodedata

_PREFIXOS_SAL = (
    "cloridrato de ", "sulfato de ", "maleato de ", "fosfato de ",
    "acetato de ", "succinato de ", "tartarato de ", "besilato de ",
    "bissulfato de ", "bromidrato de ", "citrato de ", "mesilato de ",
    "nitrato de ", "fumarato de ", "gluconato de ", "hemitartarato de ",
)

# Sufixos que indicam o sal, a hidratação ou a origem, não o fármaco.
_SUFIXOS_SAL = (
    " sodica", " potassica", " calcica", " magnesica",
    " monoidratada", " anidra", " bovina", " suina",
    " sodico", " potassico", " calcico",
    " monoidratado", " anidro",
    " de sodio", " de potassio", " de calcio",
)

# Sinônimos (nome já normalizado -> nome normalizado do catálogo).
_SINONIMOS = {
    "aas": "acido acetilsalicilico",
    "acetaminofeno": "paracetamol",
    "albuterol": "salbutamol",
    "fentanil": "fentanila",
    "noradrenalina": "norepinefrina",
    "succinilcolina": "suxametonio",
    "monoitrato de isossorbida": "mononitrato de isossorbida",
}


def normalizar_nome(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome)
    s = s.encode("ascii", "ignore").decode("ascii").lower().strip()
    s = re.sub(r"\s+", " ", s)
    for prefixo in _PREFIXOS_SAL:
        if s.startswith(prefixo):
            s = s[len(prefixo):]
            break
    mudou = True
    while mudou:
        mudou = False
        for sufixo in _SUFIXOS_SAL:
            if s.endswith(sufixo):
                s = s[: -len(sufixo)]
                mudou = True
    return _SINONIMOS.get(s, s)