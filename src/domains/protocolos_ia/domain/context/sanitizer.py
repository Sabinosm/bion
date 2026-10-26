"""Este arquivo remove identificadores comuns de texto livre e limita o tamanho dos valores que seguem para a LLM."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

MARCADOR_REMOVIDO = "[dado removido]"
LIMITE_TEXTO = 1000
LIMITE_ITENS_LISTA = 50
LIMITE_CHAVES_DICT = 50
PROFUNDIDADE_MAXIMA = 6

_PADROES = (
    re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    re.compile(r"\b\d{5}-\d{3}\b"),
    re.compile(r"(?<!\d)(?:\+?55[\s-]?)?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}(?!\d)"),
    re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-?[\dXx]\b"),
)
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def limpar_texto(valor: str, limite: int = LIMITE_TEXTO) -> str:
    """Esta função normaliza, mascara identificadores conhecidos e trunca um texto livre."""
    texto = unicodedata.normalize("NFC", valor)
    texto = _CONTROLE.sub("", texto).strip()
    for padrao in _PADROES:
        texto = padrao.sub(MARCADOR_REMOVIDO, texto)
    return texto[:limite]


def limpar_estrutura(valor: Any, _profundidade: int = 0) -> Any:
    """Esta função aplica limpar_texto a toda string de uma estrutura JSON, com limites de profundidade e tamanho."""
    if _profundidade > PROFUNDIDADE_MAXIMA:
        return None
    if isinstance(valor, str):
        return limpar_texto(valor)
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, dict):
        saida = {}
        for chave, item in list(valor.items())[:LIMITE_CHAVES_DICT]:
            saida[limpar_texto(str(chave), 80)] = limpar_estrutura(item, _profundidade + 1)
        return saida
    if isinstance(valor, (list, tuple)):
        return [limpar_estrutura(x, _profundidade + 1) for x in list(valor)[:LIMITE_ITENS_LISTA]]
    return limpar_texto(str(valor))


def texto_opcional(valor: Any, limite: int = LIMITE_TEXTO) -> str | None:
    """Esta função devolve texto limpo ou None quando o valor é vazio ou não textual."""
    if not isinstance(valor, str):
        return None
    limpo = limpar_texto(valor, limite)
    return limpo or None
