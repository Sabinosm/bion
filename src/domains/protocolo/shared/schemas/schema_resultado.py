"""Contrato de saída comum a toda ProtocoloStrategy. Nenhuma família adiciona campo aqui."""
from pydantic import BaseModel
from typing import Any


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