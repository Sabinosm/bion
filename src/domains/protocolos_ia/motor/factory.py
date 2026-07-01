"""Factory que escolhe o motor de protocolo correto pela sigla do catalogo."""

from .mts import MtsProtocolo
from .news2 import News2Protocolo
from .personalizado import ProtocoloPersonalizado


class ProtocoloFactory:
    _map = {"MTS": MtsProtocolo, "NEWS2": News2Protocolo, "PP": ProtocoloPersonalizado}

    def criar(self, catalogo):
        cls = self._map.get(catalogo.sigla)
        if not cls:
            raise ValueError(f"Protocolo não suportado: {catalogo.sigla}")
        return cls()
