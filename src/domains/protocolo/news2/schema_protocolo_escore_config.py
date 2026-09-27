"""Valida a estrutura de protocolo_escore_config (família 'escore-ponderado').

Serve o NEWS2 hoje; qualquer futuro escore por soma de parâmetros
(qSOFA, Glasgow, Apgar) reaproveita este mesmo schema.
"""
from pydantic import BaseModel, field_validator


class FaixaPontuacao(BaseModel):
    """Faixa numérica (usada por tipo_campo='numero')."""
    valor_min: float | None = None
    valor_max: float | None = None
    pontos: int

    @field_validator("pontos")
    @classmethod
    def pontos_dentro_da_escala(cls, v: int) -> int:
        if not (0 <= v <= 3):
            raise ValueError("pontos deve estar entre 0 e 3 (escala NEWS2)")
        return v


class OpcaoEnum(BaseModel):
    """Opção categórica (usada por tipo_campo='enum'), ex: estados do ACVPU."""
    valor: str        # chave enviada pelo front, ex: "alerta", "confusao"
    rotulo: str        # texto exibido, ex: "Alerta"
    pontos: int

    @field_validator("pontos")
    @classmethod
    def pontos_dentro_da_escala(cls, v: int) -> int:
        if not (0 <= v <= 3):
            raise ValueError("pontos deve estar entre 0 e 3 (escala NEWS2)")
        return v


class ParametroEscore(BaseModel):
    campo: str
    rotulo: str
    unidade: str | None = None
    tipo_campo: str = "numero"      # "numero" ou "enum"
    escala: str | None = None
    faixas: list[FaixaPontuacao] = []     # usado quando tipo_campo == "numero"
    opcoes: list[OpcaoEnum] = []          # usado quando tipo_campo == "enum"