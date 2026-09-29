"""Registro familia -> avaliador. Adicionar uma familia nova e uma funcao
nova + uma linha aqui; nenhuma familia existente e tocada."""
from .classificador_protocolo_composto import avaliar_classificador
from .pontuador_protocolo_composto import avaliar_pontuador
from .regra_protocolo_composto import avaliar_regra

AVALIADORES = {
    "pontuador": avaliar_pontuador,
    "classificador": avaliar_classificador,
    "regra": avaliar_regra,
}
