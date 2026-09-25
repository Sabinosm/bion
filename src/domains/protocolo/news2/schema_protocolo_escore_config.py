"""Valida a estrutura de protocolo_escore_config (família 'escore-ponderado').

Serve o NEWS2 hoje; qualquer futuro escore por soma de parâmetros
(qSOFA, Glasgow, Apgar) reaproveita este mesmo schema.
"""
from pydantic import BaseModel, field_validator


class FaixaPontuacao(BaseModel):
    valor_min: float | None = None   # None = sem limite inferior
    valor_max: float | None = None   # None = sem limite superior
    pontos: int

    @field_validator("pontos")
    @classmethod
    def pontos_dentro_da_escala(cls, v: int) -> int:
        if not (0 <= v <= 3):
            raise ValueError("pontos deve estar entre 0 e 3 (escala NEWS2)")
        return v


class ParametroEscore(BaseModel):
    campo: str                       # chave usada em 'respostas' (ex: "frequencia_respiratoria")
    rotulo: str                      # texto exibido ao usuário (ex: "Frequência respiratória")
    unidade: str | None = None       # ex: "irpm", "%", "bpm", "°C"
    tipo_campo: str = "numero"       # motor só aceita "numero" ou "enum" (ex: nível de consciência)
    escala: str | None = None        # discrimina SpO2 Scale 1 vs Scale 2; None para os demais parâmetros
    faixas: list[FaixaPontuacao]


class RegraOverride(BaseModel):
    condicao: str                    # identificador fixo interpretado pelo motor, ex: "qualquer_parametro_score_3"
    acao: str                        # ex: "escalonamento_imediato"


class FaixaInterpretacao(BaseModel):
    total_min: int
    total_max: int
    categoria: str                   # ex: "baixo", "medio", "alto"
    acao_recomendada: str


class SchemaEscoreConfig(BaseModel):
    schema_version: str
    parametros: list[ParametroEscore]
    regra_override: RegraOverride | None = None
    faixas_interpretacao: list[FaixaInterpretacao]