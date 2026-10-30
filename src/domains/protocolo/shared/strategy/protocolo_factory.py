"""protocolo_factory.py

Ponto único de decisão de qual estratégia de cálculo usar, a partir do
`tipo_protocolo` cadastrado no catálogo. Registrar uma nova família é
adicionar uma linha ao registro.
"""
from ...news2.protocolo_escore_ponderado import EscorePonderadoStrategy
from ...protocolo_composto.protocolo_composto_strategy import ProtocoloCompostoStrategy
from ..exceptions_protocolo import EstruturaInvalida
from .base import ProtocoloStrategy


class ProtocoloFactory:
    _registro: dict[str, type[ProtocoloStrategy]] = {
        EscorePonderadoStrategy.TIPO_PROTOCOLO: EscorePonderadoStrategy,
        ProtocoloCompostoStrategy.TIPO_PROTOCOLO: ProtocoloCompostoStrategy,
    }

    @classmethod
    def obter(cls, tipo_protocolo: str) -> ProtocoloStrategy:
        """Instancia a estratégia registrada para o tipo.

        Raises:
            EstruturaInvalida: se não houver estratégia registrada para o tipo.
        """
        classe = cls._registro.get(tipo_protocolo)
        if classe is None:
            raise EstruturaInvalida(f"Nenhuma strategy registrada para tipo_protocolo='{tipo_protocolo}'")
        return classe()
