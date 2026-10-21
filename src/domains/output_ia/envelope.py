"""Parte do output que o SISTEMA preenche (a IA nao): snapshot do envio e
metadados da resposta. Devolve dicts com nomes de coluna de OutputBion, sem
depender de SQLAlchemy.

Ciclo de OutputBion (uma linha por envio, criada ANTES da chamada):
    1. colunas_envio(input_model)        -> cria a linha (output_ia_json fica NULL)
    2. chama a IA e valida com interpretar(...)
    3. se ok: colunas_resposta(output, ...) -> atualiza a linha, e
              PrescricaoIAService.registrar_proposta(uuid_atendimento, output.proposta, ...)
       se nao: nao atualiza; NULL = enviado sem resposta valida

A gravacao das linhas de prescricao NAO esta aqui: e do PrescricaoIAService.
"""
from __future__ import annotations

import json

from .schema import OutputIA


def colunas_envio(input_model) -> dict:
    """Snapshot congelado do que a IA recebe. A ida e volta por JSON garante
    uma copia independente e 100% serializavel."""
    snapshot = json.loads(json.dumps(input_model.to_dict(), ensure_ascii=False))
    return {"input_ia_json": snapshot, "versao_input_model": input_model.VERSAO}


def _indice(v) -> float | None:
    return None if v is None else round(float(v), 2)


def colunas_resposta(output: OutputIA, versao_modelo_ia: str, *,
                     indice_completude: float | None = None,
                     indice_confianca: float | None = None) -> dict:
    """Os indices ficam por conta de quem chama (a IA nao os preenche)."""
    return {
        "output_ia_json": output.model_dump(mode="json"),
        "versao_modelo_ia": versao_modelo_ia,
        "indice_completude": _indice(indice_completude),
        "indice_confianca": _indice(indice_confianca),
    }
