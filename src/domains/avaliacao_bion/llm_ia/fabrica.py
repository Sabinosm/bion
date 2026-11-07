"""fabrica.py

Fábrica de clientes de IA (Strategy + Factory). A estratégia é o contrato de cliente; cada fornecedor é
uma classe registrada por decorador com o nome do provedor. Quem usa pede o cliente pelo nome, ou direto
do ambiente, e não conhece a classe concreta. Fornecedor novo = um arquivo em provedores/ com o
decorador, sem mexer no resto.

Ambiente:
    BION_IA_PROVEDOR   gemini | anthropic | mock | falso | indisponivel
    BION_IA_MODELO     modelo do Gemini (o Anthropic usa LLM_MODEL)
    GEMINI_API_KEY     chave do Gemini (nunca no código nem no repositório)
    LLM_*              chave, modelo, retry e breaker (ver config.py)

Sem BION_IA_PROVEDOR, o cliente padrão segue o caminho histórico de produção: o provedor sai de
LLM_PROVIDER (anthropic ou mock) e o cliente só é criado na primeira chamada. Retry e circuit breaker
dos provedores reais usam LLM_MAX_RETRIES, LLM_BREAKER_FALHAS e LLM_BREAKER_RESET_SEGUNDOS.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from typing import Callable, Mapping, Optional

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


def cliente_do_ambiente(env: Optional[Mapping[str, str]] = None) -> ClienteIA:
    """Cliente pelo nome em BION_IA_PROVEDOR; sem a variável, 'indisponivel'."""
    env = os.environ if env is None else env
    nome = env.get("BION_IA_PROVEDOR", "indisponivel")
    config = {}
    if nome.strip().lower() == "gemini":
        config["modelo"] = env.get("BION_IA_MODELO")
    return criar_cliente(nome, **config)


def cliente_padrao(env: Optional[Mapping[str, str]] = None) -> ClienteIA:
    """Porta única de produção: BION_IA_PROVEDOR quando definido; senão o caminho histórico por LLM_PROVIDER."""
    env = os.environ if env is None else env
    if env.get("BION_IA_PROVEDOR"):
        return cliente_do_ambiente(env)
    from .provedores.anthropic_turno import ClienteIAConfiguravel
    return ClienteIAConfiguravel()
