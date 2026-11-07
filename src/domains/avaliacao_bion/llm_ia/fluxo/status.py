"""Status de OutputBion (coluna status) e codigos de erro (coluna erro_codigo)."""
PROCESSANDO, CONCLUIDO, FALHOU = "processando", "concluido", "falhou"

# erro_codigo
from ..codigos import IA_INDISPONIVEL, RESPOSTA_INVALIDA  # noqa: F401  (definidos no llm_ia)
REGISTRO_PROPOSTA = "registro_proposta"      # a IA respondeu, mas o rascunho nao foi gravado
FILA_INDISPONIVEL = "fila_indisponivel"      # nao foi possivel enfileirar
EXPIRADO = "expirado"                        # ficou 'processando' alem do TTL (tarefa perdida)
INTERNO = "interno"

# Texto para o medico por erro_codigo (sem conteudo clinico e sem detalhe tecnico do provedor)
MENSAGENS_ERRO = {
    IA_INDISPONIVEL: "O assistente de IA está temporariamente indisponível. Nenhuma sugestão foi gerada; "
                     "tente novamente em alguns minutos ou siga com a prescrição manual.",
    RESPOSTA_INVALIDA: "O assistente de IA não conseguiu produzir uma sugestão válida. Nenhuma sugestão foi gerada; "
                       "tente novamente ou siga com a prescrição manual.",
    REGISTRO_PROPOSTA: "A sugestão da IA não pôde ser salva. Tente novamente ou siga com a prescrição manual.",
    FILA_INDISPONIVEL: "Não foi possível iniciar a avaliação agora. Tente novamente em alguns minutos.",
    EXPIRADO: "A avaliação demorou além do esperado e foi cancelada. Tente novamente.",
    INTERNO: "Ocorreu um erro interno na avaliação. Tente novamente ou siga com a prescrição manual.",
}


def mensagem_do_erro(erro_codigo: str | None) -> str | None:
    """Mensagem ao medico para um erro_codigo; None sem erro; texto generico para codigo desconhecido."""
    if not erro_codigo:
        return None
    return MENSAGENS_ERRO.get(erro_codigo, MENSAGENS_ERRO[INTERNO])
