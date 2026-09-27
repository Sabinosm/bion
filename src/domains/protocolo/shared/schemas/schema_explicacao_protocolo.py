"""Schema de validação da explicação obrigatória de todo protocolo.
Usado só no momento do seed (Caminho A) -- nunca em rota, nunca em runtime."""

from pydantic import BaseModel


class ExplicacaoProtocolo(BaseModel):
    o_que_e: str
    quando_usar: str
    como_interpretar: str