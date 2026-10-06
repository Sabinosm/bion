"""Valida a estrutura de protocolo_escore_config (família 'escore-ponderado').

Serve o NEWS2 hoje; qualquer futuro escore por soma de parâmetros
(qSOFA, Glasgow, Apgar) reaproveita este mesmo schema.

Exemplo de estrutura esperada (já desserializada):

    parametros = [
        {"campo": "freq_respiratoria", "rotulo": "Freq. respiratória", "unidade": "irpm",
         "tipo_campo": "numero",
         "faixas": [{"valor_max": 8, "pontos": 3},
                    {"valor_min": 9, "valor_max": 11, "pontos": 1},
                    {"valor_min": 12, "valor_max": 20, "pontos": 0},
                    {"valor_min": 21, "valor_max": 24, "pontos": 2},
                    {"valor_min": 25, "pontos": 3}]},
        {"campo": "nivel_consciencia", "rotulo": "Nível de consciência", "tipo_campo": "enum",
         "opcoes": [{"valor": "alerta", "rotulo": "Alerta", "pontos": 0},
                    {"valor": "confusao", "rotulo": "Confusão", "pontos": 3}]},
    ]
    regra_override = {"pontos_minimos": 3, "descricao": "Qualquer parâmetro isolado com 3 pontos"}
    faixas_interpretacao = [
        {"categoria": "baixo",  "escore_min": 0, "escore_max": 4, "acao_recomendada": "..."},
        {"categoria": "medio",  "escore_min": 5, "escore_max": 6, "acao_recomendada": "..."},
        {"categoria": "alto",   "escore_min": 7, "acao_recomendada": "..."},
        {"categoria": "baixo_medio", "aplicada_por_override": True, "escore_max": 4, "acao_recomendada": "..."},
    ]
"""
import json
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

PONTOS_MIN = 0
PONTOS_MAX = 3  # escala NEWS2; ajuste se um futuro escore (ex: Glasgow) precisar de mais


def _validar_pontos(v: int) -> int:
    if not (PONTOS_MIN <= v <= PONTOS_MAX):
        raise ValueError(f"pontos deve estar entre {PONTOS_MIN} e {PONTOS_MAX} (escala NEWS2)")
    return v


def _json_se_texto(v: Any) -> Any:
    """Aceita tanto JSON em texto quanto o objeto já desserializado (coluna db.JSON)."""
    if isinstance(v, (str, bytes)):
        return json.loads(v)
    return v


# ---------------------------------------------------------------------------
# Parâmetros
# ---------------------------------------------------------------------------

class FaixaPontuacao(BaseModel):
    """Faixa numérica (usada por tipo_campo='numero'). Limites inclusivos; None = aberto."""
    valor_min: float | None = None
    valor_max: float | None = None
    pontos: int

    @field_validator("pontos")
    @classmethod
    def pontos_dentro_da_escala(cls, v: int) -> int:
        return _validar_pontos(v)

    @model_validator(mode="after")
    def min_menor_ou_igual_max(self):
        if (self.valor_min is not None and self.valor_max is not None
                and self.valor_min > self.valor_max):
            raise ValueError("valor_min não pode ser maior que valor_max")
        return self


class OpcaoEnum(BaseModel):
    """Opção categórica (usada por tipo_campo='enum'), ex: estados do ACVPU."""
    valor: str        # chave enviada pelo front, ex: "alerta", "confusao"
    rotulo: str       # texto exibido, ex: "Alerta"
    pontos: int

    @field_validator("pontos")
    @classmethod
    def pontos_dentro_da_escala(cls, v: int) -> int:
        return _validar_pontos(v)


class ParametroEscore(BaseModel):
    campo: str
    rotulo: str
    unidade: str | None = None
    tipo_campo: Literal["numero", "enum"] = "numero"
    escala: str | None = None
    faixas: list[FaixaPontuacao] = []     # usado quando tipo_campo == "numero"
    opcoes: list[OpcaoEnum] = []          # usado quando tipo_campo == "enum"

    @model_validator(mode="after")
    def consistencia_por_tipo(self):
        if self.tipo_campo == "numero":
            if not self.faixas:
                raise ValueError(f"'{self.campo}': tipo 'numero' exige ao menos uma faixa")
            if self.opcoes:
                raise ValueError(f"'{self.campo}': tipo 'numero' não deve ter opcoes")
            self._checar_sobreposicao()
        else:
            if not self.opcoes:
                raise ValueError(f"'{self.campo}': tipo 'enum' exige ao menos uma opcao")
            if self.faixas:
                raise ValueError(f"'{self.campo}': tipo 'enum' não deve ter faixas")
            valores = [o.valor for o in self.opcoes]
            if len(valores) != len(set(valores)):
                raise ValueError(f"'{self.campo}': valores de opcao duplicados")
        return self

    def _checar_sobreposicao(self) -> None:
        ordenadas = sorted(
            self.faixas,
            key=lambda f: float("-inf") if f.valor_min is None else f.valor_min,
        )
        for anterior, atual in zip(ordenadas, ordenadas[1:]):
            max_ant = float("inf") if anterior.valor_max is None else anterior.valor_max
            min_atu = float("-inf") if atual.valor_min is None else atual.valor_min
            
            # CORREÇÃO: > em vez de >=
            if max_ant > min_atu:
                raise ValueError(f"'{self.campo}': faixas sobrepostas")


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------

class RegraOverride(BaseModel):
    """Regra que força uma classificação independente da soma total.

    NEWS2: qualquer parâmetro isolado com 3 pontos dispara o override.
    A categoria resultante é a faixa de interpretação marcada com
    aplicada_por_override=True.
    """
    tipo: Literal["parametro_individual"] = "parametro_individual"
    pontos_minimos: int = 3
    descricao: str | None = None

    @field_validator("pontos_minimos")
    @classmethod
    def pontos_dentro_da_escala(cls, v: int) -> int:
        return _validar_pontos(v)


# ---------------------------------------------------------------------------
# Interpretação
# ---------------------------------------------------------------------------

class FaixaInterpretacao(BaseModel):
    """Faixa do escore total -> categoria + ação. escore_max=None = aberto."""
    categoria: str
    escore_min: int | None = None
    escore_max: int | None = None
    acao_recomendada: str | None = None
    # True: só vale quando o override dispara E escore_total <= escore_max (None = sempre).
    # Acima disso a faixa normal do total já é mais grave e prevalece.
    aplicada_por_override: bool = False

    @model_validator(mode="after")
    def consistencia(self):
        if self.aplicada_por_override:
            return self
        if (self.escore_min is not None and self.escore_max is not None
                and self.escore_min > self.escore_max):
            raise ValueError(f"'{self.categoria}': escore_min maior que escore_max")
        return self


# ---------------------------------------------------------------------------
# Raiz
# ---------------------------------------------------------------------------

class SchemaEscoreConfig(BaseModel):
    schema_version: str
    parametros: list[ParametroEscore]
    regra_override: RegraOverride | None = None
    faixas_interpretacao: list[FaixaInterpretacao]

    # aceita JSON em texto OU já desserializado (db.JSON devolve list/dict)
    @field_validator("parametros", "regra_override", "faixas_interpretacao", mode="before")
    @classmethod
    def aceitar_json_em_texto(cls, v: Any) -> Any:
        return _json_se_texto(v)

    @model_validator(mode="after")
    def validar_estrutura(self):
        if not self.parametros:
            raise ValueError("o protocolo precisa ter ao menos um parametro")
        campos = [p.campo for p in self.parametros]
        if len(campos) != len(set(campos)):
            raise ValueError("campos de parametro duplicados")

        if not self.faixas_interpretacao:
            raise ValueError("o protocolo precisa ter ao menos uma faixa de interpretação")

        normais = [f for f in self.faixas_interpretacao if not f.aplicada_por_override]
        if not normais:
            raise ValueError("é preciso ao menos uma faixa de interpretação normal (sem override)")
        ordenadas = sorted(
            normais,
            key=lambda f: float("-inf") if f.escore_min is None else f.escore_min,
        )
        for anterior, atual in zip(ordenadas, ordenadas[1:]):
            max_ant = float("inf") if anterior.escore_max is None else anterior.escore_max
            min_atu = float("-inf") if atual.escore_min is None else atual.escore_min
            
            # CORREÇÃO: > em vez de >=
            if max_ant > min_atu:
                raise ValueError("faixas de interpretação sobrepostas")

        if self.regra_override is not None:
            n_override = sum(f.aplicada_por_override for f in self.faixas_interpretacao)
            if n_override != 1:
                raise ValueError(
                    "com regra_override é preciso exatamente uma faixa com aplicada_por_override=true"
                )
        return self
