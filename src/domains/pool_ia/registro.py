"""Registro de metodos da pool: cada metodo se registra com @metodo(...) num
arquivo metodos_*.py. Adicionar metodo = escrever uma funcao decorada, em
arquivo novo ou existente; a descoberta e automatica.

CONTRATO de todo metodo:
  - so LEITURA: chama o repositorio respectivo (via ctx) e nunca grava;
  - assinatura f(ctx, args) -> Retorno, com `args` validado pelo modelo Args;
  - nao recebe empresa/paciente/atendimento da IA: isso vem do `ctx`, preenchido pelo sistema.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel


@dataclass(frozen=True)
class Retorno:
    """O que um metodo devolve. `dados` vai para a IA; o resto e do sistema."""
    dados: Any
    medicamentos: frozenset[str] = frozenset()   # uuid_catalogo que a IA pode referenciar a partir de agora
    exames: frozenset[str] = frozenset()         # uuid_exame idem
    resumo: Any = None                           # versao compacta para a auditoria (default: {"n": ...})
    hash_conteudo: str | None = None             # para texto longo: prova do que a IA viu


@dataclass(frozen=True)
class Metodo:
    nome: str
    grupo: str        # nome do arquivo sem o prefixo "metodos_" (ex.: busca_medicamentos)
    descricao: str
    args: type[BaseModel]
    fn: Callable


REGISTRO: dict[str, Metodo] = {}


def metodo(nome: str, descricao: str, args: type[BaseModel]):
    def decorar(fn):
        atual = REGISTRO.get(nome)
        if atual is not None and atual.fn.__module__ != fn.__module__:
            raise ValueError(f"metodo '{nome}' ja registrado em {atual.fn.__module__}")
        grupo = fn.__module__.rsplit(".", 1)[-1].removeprefix("metodos_")
        REGISTRO[nome] = Metodo(nome, grupo, descricao, args, fn)
        return fn
    return decorar


_descoberto = False


def descobrir() -> dict[str, Metodo]:
    global _descoberto
    if not _descoberto:
        pkg = importlib.import_module(__package__)
        for m in pkgutil.iter_modules(pkg.__path__):
            if m.name.startswith("metodos_"):
                importlib.import_module(f"{pkg.__name__}.{m.name}")
        _descoberto = True
    return dict(sorted(REGISTRO.items()))
