"""avaliadores/__init__.py

Registro família -> avaliador. Adicionar uma família nova é criar uma função
de avaliação e acrescentar uma linha aqui; nenhuma família existente é tocada.
"""
from .classificador_protocolo_composto import avaliar_classificador
from .pontuador_protocolo_composto import avaliar_pontuador
from .regra_protocolo_composto import avaliar_regra

AVALIADORES = {
    "pontuador": avaliar_pontuador,
    "classificador": avaliar_classificador,
    "regra": avaliar_regra,
}
