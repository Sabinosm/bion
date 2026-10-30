"""schema_explicacao_protocolo.py

Valida a explicação obrigatória que todo protocolo carrega (o que é, quando
usar e como interpretar). Usado apenas no seed do catálogo, nunca em rota
nem em tempo de execução.
"""
from pydantic import BaseModel


class ExplicacaoProtocolo(BaseModel):
    o_que_e: str
    quando_usar: str
    como_interpretar: str
