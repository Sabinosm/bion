"""Pool: junta os metodos registrados e executa as requisicoes da IA.

A IA so PEDE; quem decide e executa e esta classe. Cada pedido vira uma
RequisicaoIA (auditoria) e, se atendido, alimenta o ledger de uuids validos
(o que a IA pode referenciar na proposta final).

Limites: MAX_RODADAS rodadas e MAX_POR_RODADA pedidos por rodada.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from src.domains.output_ia.requisicoes import RequisicaoIA, colunas_requisicoes

from .contexto import ContextoPool
from .registro import Metodo, descobrir

log = logging.getLogger(__name__)

MAX_RODADAS = 3
MAX_POR_RODADA = 5


class Pool:
    def __init__(self, ctx: ContextoPool, *, max_rodadas: int = MAX_RODADAS,
                 max_por_rodada: int = MAX_POR_RODADA, metodos: dict[str, Metodo] | None = None):
        self.ctx = ctx
        self.max_rodadas = max_rodadas
        self.max_por_rodada = max_por_rodada
        self._metodos = metodos if metodos is not None else descobrir()
        self._requisicoes: list[RequisicaoIA] = []
        self._medicamentos: set[str] = set()
        self._exames: set[str] = set()

    # ------------------------------------------------------------- catalogo
    def catalogo(self) -> list[dict]:
        """O que a IA enxerga: nome, grupo, descricao e JSON Schema dos argumentos
        (formato pronto para tool use)."""
        return [{"name": m.nome, "grupo": m.grupo, "description": m.descricao,
                 "input_schema": m.args.model_json_schema()} for m in self._metodos.values()]

    # ------------------------------------------------------------- execucao
    def executar(self, rodada: int, nome: str, argumentos: dict | None = None) -> dict:
        """Devolve {"status": "atendida", "dados": ...} ou {"status": "recusada", "motivo": ...}."""
        argumentos = argumentos if isinstance(argumentos, dict) else {}
        m = self._metodos.get(nome)
        if m is None:
            return self._recusar(rodada, nome, argumentos, "metodo inexistente na pool")
        if rodada < 1 or rodada > self.max_rodadas:
            return self._recusar(rodada, nome, argumentos, f"limite de {self.max_rodadas} rodadas")
        if sum(r.rodada == rodada for r in self._requisicoes) >= self.max_por_rodada:
            return self._recusar(rodada, nome, argumentos, f"limite de {self.max_por_rodada} pedidos por rodada")
        try:
            args = m.args.model_validate(argumentos)
        except ValidationError as e:
            motivo = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            return self._recusar(rodada, nome, argumentos, f"argumentos invalidos: {motivo}")
        try:
            ret = m.fn(self.ctx, args)
        except Exception:
            log.exception("falha no metodo da pool %s", nome)   # sem dados do paciente na mensagem
            return self._recusar(rodada, nome, argumentos, "falha ao consultar; tente outro metodo")
        self._medicamentos |= ret.medicamentos
        self._exames |= ret.exames
        resumo = ret.resumo if ret.resumo is not None else {"n": len(ret.dados) if hasattr(ret.dados, "__len__") else 1}
        self._requisicoes.append(RequisicaoIA(rodada=rodada, metodo=nome, argumentos=argumentos,
                                              status="atendida", retorno=resumo, hash_conteudo=ret.hash_conteudo))
        return {"status": "atendida", "dados": ret.dados}

    def _recusar(self, rodada: int, nome: str, argumentos: dict, motivo: str) -> dict:
        self._requisicoes.append(RequisicaoIA(rodada=max(1, rodada), metodo=nome or "?", argumentos=argumentos,
                                              status="recusada", motivo=motivo))
        return {"status": "recusada", "motivo": motivo}

    # ------------------------------------------------- ledger e auditoria
    def medicamentos_validos(self) -> set[str]:
        return set(self._medicamentos)

    def exames_validos(self) -> set[str]:
        return set(self._exames)

    def requisicoes(self) -> list[RequisicaoIA]:
        return list(self._requisicoes)

    def colunas(self) -> dict:
        """-> {"requisicoes_ia_json": [...]} para OutputBion."""
        return colunas_requisicoes(self._requisicoes)
