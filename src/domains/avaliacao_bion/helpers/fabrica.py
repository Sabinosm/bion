"""Fabrica de clientes de IA (Strategy + Factory).

`ClienteIABase` e a estrategia; cada fornecedor e uma subclasse registrada com
@provedor("nome"). Quem usa pede `criar_cliente("gemini", modelo=...)` ou
`cliente_do_ambiente()` e nao conhece a classe concreta. Fornecedor novo = um
arquivo em provedores/ com @provedor, sem mexer no resto.

Ambiente (so usado por cliente_do_ambiente):
    BION_IA_PROVEDOR   gemini | falso | indisponivel   (padrao: indisponivel)
    BION_IA_MODELO     nome do modelo do fornecedor
    GEMINI_API_KEY     chave (nunca no codigo nem no repositorio)
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from typing import Callable

from .cliente import ClienteIA

_REGISTRO: dict[str, Callable[..., ClienteIA]] = {}


class ConfigIAInvalida(ValueError):
    """Configuracao do cliente de IA ausente ou invalida."""


def provedor(nome: str):
    def registrar(fabrica):
        _REGISTRO[nome] = fabrica
        return fabrica
    return registrar


def _descobrir() -> None:
    from . import provedores
    for m in pkgutil.iter_modules(provedores.__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"{provedores.__name__}.{m.name}")


def provedores_disponiveis() -> list[str]:
    _descobrir()
    return sorted(_REGISTRO)


def criar_cliente(nome: str | None = None, **config) -> ClienteIA:
    _descobrir()
    nome = (nome or "indisponivel").strip().lower()
    if nome not in _REGISTRO:
        raise ConfigIAInvalida(f"provedor de IA desconhecido: '{nome}'. Disponiveis: {', '.join(sorted(_REGISTRO))}")
    return _REGISTRO[nome](**config)


def cliente_do_ambiente() -> ClienteIA:
    nome = os.environ.get("BION_IA_PROVEDOR", "indisponivel")
    config = {}
    if nome.strip().lower() == "gemini":
        config["modelo"] = os.environ.get("BION_IA_MODELO")
    return criar_cliente(nome, **config)
