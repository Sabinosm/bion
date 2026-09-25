"""Valida o payload que chega do front para executar qualquer protocolo."""
from pydantic import BaseModel


class SchemaExecucaoRequest(BaseModel):
    id_protocolo_catalogo: int
    id_input: int
    respostas: dict[str, str | float | int]