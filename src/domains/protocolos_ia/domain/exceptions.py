"""Exceções de domínio do módulo de IA. Todas herdam das exceções do host para que o handler global as traduza em HTTP."""
from src.core.exceptions import BionException, DadosInvalidosError

CATEGORIA_LLM_INDISPONIVEL = "llm_indisponivel"
CATEGORIA_RESPOSTA_INVALIDA = "resposta_invalida"
CATEGORIA_CONFIGURACAO_INVALIDA = "configuracao_invalida"
CATEGORIA_ERRO_DESCONHECIDO = "erro_desconhecido"


class FalhaLLMError(BionException):
    """Falha do lado da IA (provedor, resposta, prompt ou configuração). O caso de uso a converte em fallback sem diagnóstico."""

    status_code = 502
    categoria = CATEGORIA_ERRO_DESCONHECIDO

    def __init__(self, mensagem: str = "Falha no serviço de IA.", detalhes: str = ""):
        super().__init__(mensagem)
        self.detalhes = detalhes


class TipoAnaliseInvalidoError(DadosInvalidosError):
    """O tipo de análise pedido não possui estratégia registrada."""

    def __init__(self, tipos_validos: list[str]):
        super().__init__(
            f"tipo_analise inválido. Valores aceitos: {', '.join(tipos_validos)}.",
            campo="tipo_analise",
        )


class SerializacaoContextoError(FalhaLLMError):
    """O contexto clínico seguro não pôde ser serializado em JSON."""

    categoria = CATEGORIA_ERRO_DESCONHECIDO
    status_code = 500

    def __init__(self):
        super().__init__("Erro ao serializar o contexto clínico para análise de IA.")


class SnapshotInvalidoError(BionException):
    """O snapshot clínico congelado do atendimento está ausente ou malformado. É erro interno do servidor."""

    status_code = 500

    def __init__(self):
        super().__init__("Snapshot clínico do atendimento inválido.")
