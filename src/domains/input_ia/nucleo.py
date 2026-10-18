"""Nucleo compartilhado por todos os blocos: utilitarios, Status e Bloco.

Nao conhece nenhum dominio (paciente, atendimento, protocolo).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Iterable

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Utilitarios
# --------------------------------------------------------------------------
def limpar(v: Any) -> Any:
    """Remove None, '', [] e {} recursivamente. Mantem False e 0."""
    if isinstance(v, dict):
        out = {k: limpar(x) for k, x in v.items()}
        return {k: x for k, x in out.items() if x not in (None, "", [], {})}
    if isinstance(v, (list, tuple)):
        out = [limpar(x) for x in v]
        return [x for x in out if x not in (None, "", [], {})]
    return v


def iso(d) -> str | None:
    return d.isoformat() if d else None


def num(v) -> float | None:
    return float(v) if v is not None else None


def idade(nasc: date | None, ref: date) -> tuple[int | None, int | None]:
    """(anos, meses totais). (None, None) sem data de nascimento."""
    if not nasc:
        return None, None
    anos = ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))
    meses = (ref.year - nasc.year) * 12 + (ref.month - nasc.month) - (ref.day < nasc.day)
    return anos, meses


def linhas(v: Any, ind: int = 0) -> Iterable[str]:
    pad = "  " * ind
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, (dict, list)) and x:
                yield f"{pad}{k}:"
                yield from linhas(x, ind + 1)
            else:
                yield f"{pad}{k}: {x}"
    elif isinstance(v, list):
        for x in v:
            if isinstance(x, dict):
                yield f"{pad}-"
                yield from linhas(x, ind + 1)
            else:
                yield f"{pad}- {x}"
    else:
        yield f"{pad}{v}"


# --------------------------------------------------------------------------
# Status (binario do atendimento -> o que a IA le)
# --------------------------------------------------------------------------
class Status(Enum):
    INFORMADO = "informado"
    NEGADO = "negado"                # perguntado, paciente nega
    NAO_INFORMADO = "nao_informado"  # ninguem perguntou / nao coletado


_MAPA = {
    "preenchido": Status.INFORMADO,
    "nega": Status.NEGADO,
    "nao-coletado": Status.NAO_INFORMADO,
}


def resolver_status(itens, binario: dict | None, chave: str) -> tuple[Status, bool]:
    """Retorna (status, inconsistente). Registros reais sempre vencem o
    binario; 'preenchido' sem registro nunca vira 'nenhum' (lado seguro)."""
    bruto = ((binario or {}).get(chave) or {}).get("estado")
    if bruto == "requer-revisao":
        # Dado do paciente mudou e ninguém confirmou: o InputModel NÃO aceita
        # (nem os itens vão para a IA). Sempre inconsistente.
        return Status.NAO_INFORMADO, True
    declarado = _MAPA.get(bruto, Status.NAO_INFORMADO)
    if itens:
        return Status.INFORMADO, declarado is not Status.INFORMADO
    if declarado is Status.INFORMADO:
        return Status.NAO_INFORMADO, True
    return declarado, False


# --------------------------------------------------------------------------
# Bloco (contrato unico de toda caixa pequena)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Bloco:
    nome: str
    dados: dict
    lacunas: tuple[str, ...] = ()
    inconsistente: bool = False

    def to_dict(self) -> dict:
        return self.dados

    def faltando(self) -> list[str]:
        return list(self.lacunas)

    def to_prompt(self) -> str:
        return "\n".join([f"## {self.nome}", *linhas(self.dados)])


def bloco_lista(nome: str, itens: list[dict], binario: dict | None,
                chave_itens: str = "itens") -> Bloco:
    """Bloco de lista conferida pelo binario (alergias, medicamentos, ...)."""
    status, inconsistente = resolver_status(itens, binario, nome)
    if inconsistente:
        log.warning("binario diverge dos registros em '%s' (status=%s)", nome, status.value)
    if status is Status.INFORMADO:
        dados = {chave_itens: itens}
    elif status is Status.NEGADO:
        dados = {"status": "paciente_nega"}
    else:
        dados = {"status": "nao_informado"}
    lacunas = ()
    if status is Status.NAO_INFORMADO:
        bruto = ((binario or {}).get(nome) or {}).get("estado")
        if bruto == "nao-coletado":
            motivo = "nao coletado"
        elif bruto == "requer-revisao":
            motivo = "requer revisao: dado do paciente mudou desde a ultima conferencia"
        elif bruto == "preenchido":
            motivo = "marcado como preenchido, mas sem registro"
        else:
            motivo = "conferencia pendente"
        lacunas = (f"{nome}: nao informado ({motivo})",)
    return Bloco(nome, dados, lacunas, inconsistente)
