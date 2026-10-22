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
    declarado = _MAPA.get(bruto, Status.NAO_INFORMADO)
    if itens:
        return Status.INFORMADO, declarado is not Status.INFORMADO
    if declarado is Status.INFORMADO:
        return Status.NAO_INFORMADO, True
    return declarado, False


# --------------------------------------------------------------------------
# Sinais de baixa confiabilidade (um bloco os emite; indices.py os pondera)
# --------------------------------------------------------------------------
class Sinal:
    BINARIO_DIVERGE = "binario_diverge"                  # binario e registros se contradizem
    CONFERENCIA_PENDENTE = "conferencia_pendente"        # ha registros, mas o binario nao foi conferido neste atendimento
    ALERGIA_NAO_CONFIRMADA = "alergia_nao_confirmada"
    MEDICAMENTO_SEM_CATALOGO = "medicamento_sem_catalogo"  # fora do catalogo: nao entra na checagem de interacoes
    SINAL_VITAL_FORA_DO_LIMITE = "sinal_vital_fora_do_limite"
    PROTOCOLO_INCOMPLETO = "protocolo_incompleto"
    DADO_CRITICO_AUSENTE = "dado_critico_ausente"


# --------------------------------------------------------------------------
# Bloco (contrato unico de toda caixa pequena)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Bloco:
    nome: str
    dados: dict
    lacunas: tuple[str, ...] = ()
    inconsistente: bool = False
    # Insumos dos indices (ver indices.py). esperados=0: o bloco nao entra na
    # completude (informativo ou nao se aplica a este atendimento).
    esperados: int = 0
    presentes: int = 0
    sinais: tuple[str, ...] = ()   # codigos de Sinal; cada ocorrencia conta

    def to_dict(self) -> dict:
        return self.dados

    def faltando(self) -> list[str]:
        return list(self.lacunas)

    def to_prompt(self) -> str:
        return "\n".join([f"## {self.nome}", *linhas(self.dados)])


def bloco_lista(nome: str, itens: list[dict], binario: dict | None,
                chave_itens: str = "itens", sinais: tuple[str, ...] = ()) -> Bloco:
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
    bruto = ((binario or {}).get(nome) or {}).get("estado")
    lacunas = ()
    if status is Status.NAO_INFORMADO:
        if bruto == "nao-coletado":
            motivo = "nao coletado"
        elif bruto == "preenchido":
            motivo = "marcado como preenchido, mas sem registro"
        else:
            motivo = "conferencia pendente"
        lacunas = (f"{nome}: nao informado ({motivo})",)
    sinais = tuple(sinais)
    if inconsistente:
        pendente = bruto not in _MAPA   # sem conferencia (ou estado desconhecido)
        sinais += (Sinal.CONFERENCIA_PENDENTE if (itens and pendente) else Sinal.BINARIO_DIVERGE,)
    return Bloco(nome, dados, lacunas, inconsistente,
                 esperados=1, presentes=0 if status is Status.NAO_INFORMADO else 1, sinais=sinais)
