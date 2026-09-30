"""Consolida os 10 modulos do seed numa lista unica, atribuindo indice_bit
de forma DETERMINISTICA E IMUTAVEL: a ordem desta lista e a fonte da
verdade do indice_bit de cada modulo. Uma vez publicado, um modulo NUNCA
muda de posicao aqui -- um modulo novo sempre vai ao FINAL da lista,
nunca inserido no meio (isso reordenaria os indices de todos os
seguintes e invalidaria os codigo_composicao ja gravados)."""
from .modulos_1_4 import MODULO_IMC, MODULO_PA, MODULO_PHQ9, MODULO_GAD7
from .modulos_5_7 import MODULO_AUDITC, MODULO_POLIFARMACIA, MODULO_RISCO_QUEDA
from .modulos_8_10 import MODULO_RISCO_CV, MODULO_WELLS_TEP, MODULO_ELEGIBILIDADE_ADULTO

# ORDEM FIXA -- ver docstring acima. indice_bit = posicao nesta lista.
MODULOS = [
    MODULO_IMC,                    # indice_bit 0
    MODULO_PA,                     # indice_bit 1
    MODULO_PHQ9,                   # indice_bit 2
    MODULO_GAD7,                   # indice_bit 3
    MODULO_AUDITC,                 # indice_bit 4
    MODULO_POLIFARMACIA,           # indice_bit 5
    MODULO_RISCO_QUEDA,            # indice_bit 6
    MODULO_RISCO_CV,               # indice_bit 7
    MODULO_WELLS_TEP,              # indice_bit 8
    MODULO_ELEGIBILIDADE_ADULTO,   # indice_bit 9
]

for _i, _m in enumerate(MODULOS):
    _m["indice_bit"] = _i

MODULOS_POR_SIGLA = {m["sigla"]: m for m in MODULOS}

assert len(MODULOS_POR_SIGLA) == len(MODULOS), "sigla duplicada entre modulos do seed"
