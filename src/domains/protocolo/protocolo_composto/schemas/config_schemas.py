"""Schemas do `configuracao_json` por familia. Validados SO no seed --
nunca em runtime, nunca em rota. Um JSON que nao valida aqui nunca entra
no banco.

Convencao de faixa (fixada, nao configuravel por instrumento):
    minimo INCLUSIVO, maximo EXCLUSIVO -> [min, max)
    min=None  significa "sem piso" (-infinito)
    max=None  significa "sem teto" (+infinito)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from ..logic.condicao_protocolo_composto import CondicaoInvalida, validar_estrutura


# ---------------------------------------------------------------------
# Blocos compartilhados
# ---------------------------------------------------------------------
class Faixa(BaseModel):
    min: float | None = None
    max: float | None = None
    pontos: float | None = None           # usado no pontuador; aceita fracoes (ex.: Wells usa 1.5, 3.0)
    classificacao: str | None = None     # usado no classificador
    gravidade: int | None = None         # ordem de gravidade p/ pior_categoria

    @model_validator(mode="after")
    def _minmax_coerentes(self):
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError(f"faixa invalida: min={self.min} deve ser < max={self.max}")
        return self


def _checar_cobertura_sem_buraco_nem_sobreposicao(faixas: list[Faixa], contexto: str) -> None:
    """Ordena por `min` (None tratado como -inf) e garante que o `max` de
    uma faixa bate exatamente com o `min` da proxima -- sem buraco e sem
    sobreposicao. Exige exatamente uma faixa com min=None (piso aberto) e
    exatamente uma com max=None (teto aberto)."""
    if not faixas:
        raise ValueError(f"{contexto}: lista de faixas vazia")

    ordenadas = sorted(faixas, key=lambda f: (f.min is not None, f.min))

    abertas_piso = [f for f in faixas if f.min is None]
    abertas_teto = [f for f in faixas if f.max is None]
    if len(abertas_piso) != 1:
        raise ValueError(f"{contexto}: precisa de exatamente 1 faixa com min=None (achou {len(abertas_piso)})")
    if len(abertas_teto) != 1:
        raise ValueError(f"{contexto}: precisa de exatamente 1 faixa com max=None (achou {len(abertas_teto)})")

    for anterior, atual in zip(ordenadas, ordenadas[1:]):
        if anterior.max is None:
            raise ValueError(f"{contexto}: faixa com max=None nao pode ter sucessora ({atual})")
        if atual.min is None:
            raise ValueError(f"{contexto}: faixa com min=None nao pode ter antecessora ({anterior})")
        if anterior.max != atual.min:
            raise ValueError(
                f"{contexto}: buraco ou sobreposicao entre {anterior} e {atual} "
                f"(max={anterior.max} != min={atual.min})"
            )


# ---------------------------------------------------------------------
# Pontuador
# ---------------------------------------------------------------------
class ParametroFaixas(BaseModel):
    variavel: str
    tipo: Literal["faixas"]
    faixas: list[Faixa]

    @model_validator(mode="after")
    def _valida(self):
        for f in self.faixas:
            if f.pontos is None:
                raise ValueError(f"{self.variavel}: toda faixa de pontuador exige 'pontos'")
        _checar_cobertura_sem_buraco_nem_sobreposicao(self.faixas, f"pontuador.{self.variavel}")
        return self


class ParametroMapeamento(BaseModel):
    variavel: str
    tipo: Literal["mapeamento"]
    mapa: dict[str, float]


class InterpretacaoPontuador(BaseModel):
    faixas: list[Faixa]

    @model_validator(mode="after")
    def _valida(self):
        for f in self.faixas:
            if not f.classificacao:
                raise ValueError("toda faixa de interpretacao exige 'classificacao'")
        _checar_cobertura_sem_buraco_nem_sobreposicao(self.faixas, "pontuador.interpretacao")
        return self


class InterpretacaoSegmentada(BaseModel):
    """Interpretacao do TOTAL que depende de uma variavel categorica de
    ENTRADA (ex.: corte do AUDIT-C difere por sexo biologico). A variavel
    de segmentacao precisa estar entre os campos do modulo, mas NAO entra
    na soma -- so escolhe qual conjunto de faixas usar."""
    segmentada_por: str
    por_valor: dict[str, InterpretacaoPontuador]

    @model_validator(mode="after")
    def _exige_ao_menos_um_valor(self):
        if not self.por_valor:
            raise ValueError("interpretacao segmentada exige ao menos 1 valor em 'por_valor'")
        return self


class ConfigPontuador(BaseModel):
    familia: Literal["pontuador"]
    parametros: list[ParametroFaixas | ParametroMapeamento]
    interpretacao: InterpretacaoPontuador | InterpretacaoSegmentada | None = None

    @model_validator(mode="after")
    def _sem_variavel_duplicada(self):
        vars_ = [p.variavel for p in self.parametros]
        dups = {v for v in vars_ if vars_.count(v) > 1}
        if dups:
            raise ValueError(f"variaveis repetidas nos parametros do pontuador: {dups}")
        return self

    def variaveis_usadas(self) -> set[str]:
        base = {p.variavel for p in self.parametros}
        if isinstance(self.interpretacao, InterpretacaoSegmentada):
            base.add(self.interpretacao.segmentada_por)
        return base


# ---------------------------------------------------------------------
# Classificador
# ---------------------------------------------------------------------
class ClassificadorPorFaixas(BaseModel):
    familia: Literal["classificador"]
    modo: Literal["faixas"]
    variavel: str
    categorias: list[Faixa]

    @model_validator(mode="after")
    def _valida(self):
        for c in self.categorias:
            if not c.classificacao:
                raise ValueError("toda categoria exige 'classificacao'")
        _checar_cobertura_sem_buraco_nem_sobreposicao(self.categorias, f"classificador.{self.variavel}")
        return self

    def variaveis_usadas(self) -> set[str]:
        return {self.variavel}


class RegraClassificacao(BaseModel):
    se: dict[str, Any]
    classificacao: str
    gravidade: int | None = None


class ClassificadorPorRegras(BaseModel):
    familia: Literal["classificador"]
    modo: Literal["regras"]
    regras: list[RegraClassificacao]
    padrao: dict[str, Any]

    @model_validator(mode="after")
    def _valida(self):
        if not self.regras:
            raise ValueError("classificador por regras exige ao menos 1 regra")
        if "classificacao" not in self.padrao:
            raise ValueError("'padrao' exige 'classificacao'")
        for r in self.regras:
            try:
                validar_estrutura(r.se)
            except CondicaoInvalida as ex:
                raise ValueError(f"regra invalida ({r.classificacao}): {ex}") from ex
        return self

    def variaveis_usadas(self) -> set[str]:
        vs: set[str] = set()
        for r in self.regras:
            vs |= validar_estrutura(r.se)
        return vs


ConfigClassificador = ClassificadorPorFaixas | ClassificadorPorRegras


# ---------------------------------------------------------------------
# Regra / Gatilho
# ---------------------------------------------------------------------
class SaidaRegra(BaseModel):
    classificacao: str
    motivo: str | None = None


class ConfigRegra(BaseModel):
    familia: Literal["regra"]
    condicao: dict[str, Any]
    saida_verdadeiro: SaidaRegra
    saida_falso: SaidaRegra

    @model_validator(mode="after")
    def _condicao_valida(self):
        try:
            validar_estrutura(self.condicao)
        except CondicaoInvalida as ex:
            raise ValueError(f"condicao invalida: {ex}") from ex
        return self

    def variaveis_usadas(self) -> set[str]:
        return validar_estrutura(self.condicao)


# ---------------------------------------------------------------------
# Fachada usada pelo seed: valida o JSON cru contra a familia declarada
# em catalogo_modulos.familia_calculo, e devolve o objeto tipado.
# ---------------------------------------------------------------------
_POR_FAMILIA = {
    "pontuador": ConfigPontuador,
    "classificador": None,   # resolvido por 'modo' abaixo
    "regra": ConfigRegra,
}


def validar_configuracao(familia: str, bruto: dict[str, Any]):
    if familia == "classificador":
        modo = bruto.get("modo")
        if modo == "faixas":
            return ClassificadorPorFaixas.model_validate(bruto)
        if modo == "regras":
            return ClassificadorPorRegras.model_validate(bruto)
        raise ValueError(f"classificador: 'modo' invalido ou ausente: {modo!r}")

    cls = _POR_FAMILIA.get(familia)
    if cls is None:
        raise ValueError(f"familia desconhecida: {familia!r}")
    return cls.model_validate(bruto)