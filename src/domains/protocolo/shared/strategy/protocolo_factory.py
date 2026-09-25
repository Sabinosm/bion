"""Único ponto de decisão de qual Strategy usar, a partir de tipo_protocolo."""
from .base import ProtocoloStrategy
from ...news2.strategy.protocolo_escore_ponderado import ProtocoloEscorePonderadoStrategy


class ProtocoloFactory:
    _registro: dict[str, type[ProtocoloStrategy]] = {
        "escore-ponderado": ProtocoloEscorePonderadoStrategy
    }

    @classmethod
    def obter(cls, tipo_protocolo: str) -> ProtocoloStrategy:
        classe = cls._registro.get(tipo_protocolo)
        if classe is None:
            raise ValueError(f"Nenhuma strategy registrada para tipo_protocolo='{tipo_protocolo}'")
        return classe()