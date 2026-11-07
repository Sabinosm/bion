"""codigos.py

Códigos de erro que o processamento de IA devolve quando não consegue entregar uma avaliação. São os mesmos textos gravados em erro_codigo no contrato com o front; o módulo que persiste a avaliação reexporta estes valores junto com os demais códigos que são dele.
"""
IA_INDISPONIVEL = "ia_indisponivel"          # o modelo nao respondeu / nao ha modelo configurado
RESPOSTA_INVALIDA = "resposta_invalida"      # esgotou as tentativas de uma resposta valida
