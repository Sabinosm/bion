"""Registro de blocos: cada caixa pequena se registra com @bloco(...) e o
InputModel monta o input percorrendo o registro.

Adicionar um bloco  = criar um arquivo numa pasta de grupo
                      (dados_clinicos/, atendimento/, protocolar/) com uma
                      funcao decorada.
Adicionar um grupo  = criar uma pasta nova com __init__.py.
Nada mais muda: a descoberta e automatica (arquivos iniciados por "_" sao
ignorados e servem de apoio compartilhado dentro do grupo).
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Fabrica:
    nome: str       # igual ao Bloco.nome que a funcao devolve
    grupo: str      # nome da pasta onde o arquivo mora
    ordem: int      # posicao no prompt
    descricao: str  # o que o bloco entrega (serve de descricao de metodo)
    fn: Callable    # f(atendimento) -> Bloco


REGISTRO: dict[str, Fabrica] = {}


def bloco(nome: str, ordem: int, descricao: str):
    """Registra uma fabrica de bloco. O grupo vem da pasta do arquivo."""
    def decorar(fn):
        atual = REGISTRO.get(nome)
        if atual is not None and atual.fn.__module__ != fn.__module__:
            raise ValueError(f"bloco '{nome}' ja registrado em {atual.fn.__module__}")
        partes = fn.__module__.split(".")
        grupo = partes[-2] if len(partes) > 1 else "outros"
        REGISTRO[nome] = Fabrica(nome, grupo, ordem, descricao, fn)
        return fn
    return decorar


_descoberto = False


def descobrir() -> None:
    """Importa todo arquivo de bloco de toda pasta de grupo (idempotente)."""
    global _descoberto
    if _descoberto:
        return
    raiz = importlib.import_module(__package__)
    for g in pkgutil.iter_modules(raiz.__path__):
        if not g.ispkg or g.name.startswith("_"):
            continue
        pkg = importlib.import_module(f"{raiz.__name__}.{g.name}")
        for m in pkgutil.iter_modules(pkg.__path__):
            if not m.name.startswith("_"):
                importlib.import_module(f"{pkg.__name__}.{m.name}")
    _descoberto = True


def fabricas() -> list[Fabrica]:
    descobrir()
    return sorted(REGISTRO.values(), key=lambda f: (f.ordem, f.nome))
