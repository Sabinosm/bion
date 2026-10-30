"""schema_resultado.py

Contrato de saída comum a toda família de protocolo. O resultado de qualquer
cálculo é convertido para este formato, o que permite persistir e exibir
execuções de forma uniforme. Nenhuma família adiciona campos aqui; o que for
específico de uma família vai em `metadata`.
"""
from typing import Any

from pydantic import BaseModel


class PassoTrilha(BaseModel):
    rotulo: str
    valor_observado: str
    peso_ou_resultado: str
    ordem: int


class SchemaResultado(BaseModel):
    classificacao: str
    trilha_explicativa: list[PassoTrilha]
    dados_ausentes: list[str]
    metadata: dict[str, Any]
