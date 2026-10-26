"""Este arquivo define a resposta bruta devolvida por um provedor, antes de qualquer validação clínica."""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class RawLLMResponse:
    texto: str
    modelo: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    motivo_parada: Optional[str] = None
    blocos_conteudo: Tuple[dict, ...] = ()

    def __repr__(self) -> str:
        return f"RawLLMResponse(modelo={self.modelo!r}, tokens_entrada={self.tokens_entrada}, tokens_saida={self.tokens_saida})"
