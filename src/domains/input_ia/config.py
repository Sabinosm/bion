"""Config: parametro do input (nao e conteudo clinico)."""
from __future__ import annotations

from dataclasses import dataclass

IDIOMA_PADRAO = "pt-BR"


@dataclass(frozen=True)
class Config:
    """Preferencias do usuario que influenciam o input para a IA. Hoje so o
    idioma; tema, fonte e protocolos acompanhados nao interessam a IA."""
    idioma: str = IDIOMA_PADRAO

    @classmethod
    def de_dict(cls, cfg: dict | None) -> "Config":
        """Aceita o to_dict() de Configuracao:
        {"preferencias": {"linguagem": ["pt-BR", ...]}, ...}. Usa o primeiro
        idioma valido; ausente ou invalido cai no padrao."""
        pref = (cfg or {}).get("preferencias")
        ling = pref.get("linguagem") if isinstance(pref, dict) else None
        if isinstance(ling, (list, tuple)):
            ling = next((x for x in ling if isinstance(x, str) and x.strip()), None)
        if not isinstance(ling, str) or not ling.strip():
            return cls()
        return cls(ling.strip())
