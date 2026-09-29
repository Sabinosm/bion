"""Estruturas puras (Pydantic) do protocolo composto.

Nada aqui conhece SQLAlchemy: `carregar_estrutura` traduz os Models para
estes tipos e, a partir dali, o calculo nunca mais toca o banco.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

FamiliaModulo = Literal["pontuador", "classificador", "regra"]
TipoSaida = Literal["pontos", "categoria", "flag"]
PapelModulo = Literal["principal", "gatilho", "informativo"]
TipoAgregacao = Literal["nenhuma", "soma", "maximo", "pior_categoria", "any_flag"]
StatusModulo = Literal["calculado", "nao_calculavel", "nao_aplicavel"]

# classificacao "convencional" quando nao ha agregacao (decisao: opcao A).
# O front reconhece esta constante e renderiza metadata["modulos"] em destaque.
CLASSIFICACAO_MULTIPLOS_RESULTADOS = "multiplos-resultados"


class VariavelDef(BaseModel):
    codigo: str
    nome: str
    tipo_dado: Literal["numerico", "categorico", "booleano"]
    unidade: str | None = None
    opcoes: list[dict[str, str]] | None = None  # [{"valor", "rotulo"}]
    valor_min: float | None = None
    valor_max: float | None = None


class ModuloDef(BaseModel):
    sigla: str
    versao: str
    familia: FamiliaModulo
    tipo_saida: TipoSaida
    papel: PapelModulo = "principal"
    grupo_agregacao: str | None = None
    configuracao: dict[str, Any]
    campos: list[tuple[str, bool]] = Field(
        default_factory=list, description="(codigo_variavel, obrigatorio)"
    )


class EstruturaComposta(BaseModel):
    modulos: list[ModuloDef]
    variaveis: dict[str, VariavelDef]  # uniao, sem duplicar
    agregacao: TipoAgregacao = "nenhuma"
    regra_gatilho: dict[str, Any] | None = None
    codigo_composicao: int | None = None


class ItemTrilha(BaseModel):
    """Um passo da trilha de um modulo. O `rotulo` ja deve vir prefixado com
    a sigla do modulo na hora de concatenar (ver strategy)."""

    rotulo: str
    valor_observado: str
    contribuicao: str


class ResultadoModulo(BaseModel):
    sigla_modulo: str
    versao: str
    status: StatusModulo
    tipo_saida: TipoSaida
    valor: float | str | bool | None = None
    classificacao: str | None = None
    gravidade: int | None = None  # so classificador/pontuador com faixa
    trilha: list[ItemTrilha] = Field(default_factory=list)
    ausentes: list[str] = Field(default_factory=list)
    motivo: str | None = None
