"""Este arquivo define as falhas classificadas da infraestrutura de LLM. Mensagens nunca incluem dados clínicos, corpo de resposta ou chave de API."""
from typing import Optional

from ...domain.exceptions import (
    CATEGORIA_CONFIGURACAO_INVALIDA,
    CATEGORIA_LLM_INDISPONIVEL,
    CATEGORIA_RESPOSTA_INVALIDA,
    FalhaLLMError,
)


class ProvedorIndisponivelError(FalhaLLMError):
    """O provedor não respondeu de forma utilizável."""

    categoria = CATEGORIA_LLM_INDISPONIVEL

    def __init__(self, mensagem: str = "Provedor de IA temporariamente indisponível.", detalhes: str = ""):
        super().__init__(mensagem, detalhes)


class ErroTransitorioProvedor(ProvedorIndisponivelError):
    """Falha que pode se resolver sozinha (timeout, conexão, 429, 5xx). Elegível a retry."""

    def __init__(self, detalhes: str = "", retry_apos_segundos: Optional[float] = None):
        super().__init__(detalhes=detalhes)
        self.retry_apos_segundos = retry_apos_segundos


class ErroPermanenteProvedor(ProvedorIndisponivelError):
    """Falha que não melhora com nova tentativa (credencial, requisição inválida). Não sofre retry nem abre o breaker."""


class CircuitBreakerAbertoError(ProvedorIndisponivelError):
    """Chamadas suspensas após falhas consecutivas."""

    def __init__(self):
        super().__init__("Serviço de IA temporariamente suspenso. Tente novamente em alguns minutos.", "circuit_breaker_aberto")


class RespostaLLMInvalidaError(FalhaLLMError):
    """O provedor respondeu, mas o conteúdo não é utilizável como dado clínico."""

    categoria = CATEGORIA_RESPOSTA_INVALIDA

    def __init__(self, detalhes: str = ""):
        super().__init__("Resposta da IA em formato inválido.", detalhes)


class PromptNaoEncontradoError(FalhaLLMError):
    categoria = CATEGORIA_CONFIGURACAO_INVALIDA
    status_code = 500

    def __init__(self, detalhes: str = ""):
        super().__init__("Prompt de IA não encontrado ou inválido.", detalhes)


class ConfiguracaoLLMInvalidaError(FalhaLLMError):
    categoria = CATEGORIA_CONFIGURACAO_INVALIDA
    status_code = 500

    def __init__(self, campo: str, motivo: str):
        super().__init__("Configuração do módulo de IA inválida.", f"{campo}: {motivo}")
        self.campo = campo
