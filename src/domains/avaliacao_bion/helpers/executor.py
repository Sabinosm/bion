"""Quem roda a tarefa fora da requisicao. `enfileirar(tarefa)` nao bloqueia.

ExecutorThread: pool de threads dentro do proprio processo Flask (basta para
comecar). Se o servidor reiniciar, a tarefa em andamento se perde: o status
'processando' expira (TTL) e vira 'falhou' (erro_codigo='expirado'). Para
producao pesada, implemente Executor com sua fila e chame service.processar(tarefa).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Protocol

from .tarefa import Tarefa

log = logging.getLogger(__name__)


class Executor(Protocol):
    def enfileirar(self, tarefa: Tarefa) -> None: ...


class ExecutorThread:
    def __init__(self, processar: Callable[[Tarefa], None], max_workers: int = 2, app=None):
        self._processar = processar
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="bion")
        self._app = app

    def enfileirar(self, tarefa: Tarefa) -> None:
        app = self._app
        if app is None:
            from flask import current_app
            app = current_app._get_current_object()   # a thread precisa do app, nao do proxy
        self._pool.submit(self._rodar, app, tarefa)

    def _rodar(self, app, tarefa: Tarefa) -> None:
        with app.app_context():
            try:
                self._processar(tarefa)
            except Exception:
                log.exception("falha nao tratada na avaliacao Bion %s", tarefa.uuid_output)
            finally:
                from src.models import db
                db.session.remove()
