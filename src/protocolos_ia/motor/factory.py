"""Factory que escolhe o motor de protocolo correto pela sigla do catálogo."""

from .mts import MtsProtocolo
from .news2 import News2Protocolo
from .personalizado import ProtocoloPersonalizado


class ProtocoloFactory:
    """Cria a instância do motor Strategy correspondente à sigla do ProtocoloCatalogo."""

    _map = {"MTS": MtsProtocolo, "NEWS2": News2Protocolo, "PP": ProtocoloPersonalizado}

    def criar(self, catalogo):
        """
        Retorna uma nova instância do motor correspondente à sigla do catálogo.

        Raises:
            ValueError: se a sigla não tiver motor implementado.
        """
        cls = self._map.get(catalogo.sigla)
        if not cls:
            raise ValueError(f"Protocolo não suportado: {catalogo.sigla}")
        return cls()
