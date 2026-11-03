"""envelope.py

Parte do output que o SISTEMA preenche (a IA nao): snapshot do envio e metadados da resposta, como dicts com nomes de coluna de OutputBion, sem depender de SQLAlchemy.

Ciclo de OutputBion (uma linha por envio, criada antes da chamada): o envio nasce com status 'processando' e o snapshot do input; se a resposta for valida, recebe a resposta e as requisicoes e vira 'concluido'; se nao, vira 'falhou' com erro_codigo e output_ia_json fica NULL. A gravacao das linhas de prescricao e do PrescricaoIAService.
"""
from __future__ import annotations

import json

from .schema import OutputIA


def colunas_envio(input_model) -> dict:
    """Snapshot congelado do que a IA recebe + indices do input (calculados no
    envio: descrevem o input, nao a resposta). A ida e volta por JSON garante
    uma copia independente e 100% serializavel.

    `indices_input` fica DENTRO do snapshot por ser calculo do sistema (motivos da
    confianca, para o front); NAO faz parte do que a IA recebe."""
    snapshot = json.loads(json.dumps(input_model.to_dict(), ensure_ascii=False))
    ind = input_model.indices()
    snapshot["indices_input"] = json.loads(json.dumps(ind.to_dict(), ensure_ascii=False))
    return {"input_ia_json": snapshot, "versao_input_model": input_model.VERSAO,
            "indice_completude": _indice(ind.completude), "indice_confianca": _indice(ind.confianca)}


def _indice(v) -> float | None:
    return None if v is None else round(float(v), 2)


def colunas_resposta(output: OutputIA, versao_modelo_ia: str) -> dict:
    """Resposta valida da IA (os indices ja foram gravados no envio)."""
    return {"output_ia_json": output.model_dump(mode="json"), "versao_modelo_ia": versao_modelo_ia}
