"""Status de OutputBion (coluna status) e codigos de erro (coluna erro_codigo)."""
PROCESSANDO, CONCLUIDO, FALHOU = "processando", "concluido", "falhou"

# erro_codigo
IA_INDISPONIVEL = "ia_indisponivel"          # o modelo nao respondeu / nao ha modelo configurado
RESPOSTA_INVALIDA = "resposta_invalida"      # esgotou as tentativas de uma resposta valida
REGISTRO_PROPOSTA = "registro_proposta"      # a IA respondeu, mas o rascunho nao foi gravado
FILA_INDISPONIVEL = "fila_indisponivel"      # nao foi possivel enfileirar
EXPIRADO = "expirado"                        # ficou 'processando' alem do TTL (tarefa perdida)
INTERNO = "interno"
