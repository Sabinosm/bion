"""exceptions_protocolo.py

Exceções de configuração inconsistente dos protocolos: o cadastro (seed) do
protocolo está errado, não a resposta do profissional. Todas herdam de
BionException com status 500 e levam uma mensagem própria, segura para o
usuário, enquanto o detalhe técnico (o que exatamente está errado) vai para o
log e fica em `detalhe`. Também herdam de ValueError, para que quem já captura
ValueError (seed, testes) continue funcionando.
"""
import logging

from src.core.exceptions import BionException

logger = logging.getLogger(__name__)


class ConfiguracaoProtocoloInvalidaError(BionException, ValueError):
    """Base das exceções de configuração inconsistente de protocolo."""

    status_code = 500
    MENSAGEM_PADRAO = "A configuração deste protocolo está inconsistente. Contate o suporte."

    def __init__(self, detalhe: str = ""):
        super().__init__(self.MENSAGEM_PADRAO)
        self.detalhe = detalhe or self.MENSAGEM_PADRAO
        logger.error("%s: %s", type(self).__name__, self.detalhe)

    def __str__(self) -> str:
        return self.detalhe


class EstruturaInvalida(ConfiguracaoProtocoloInvalidaError):
    """Configuração cadastrada que não pode ser carregada ou usada: estrutura
    malformada, família sem estratégia registrada, valor sem faixa de
    interpretação ou configuração que não passa na validação do schema."""

    MENSAGEM_PADRAO = "A estrutura cadastrada para este protocolo está inconsistente. Contate o suporte."
