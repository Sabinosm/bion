"""
Contratos do motor de protocolos (padrao Strategy + Factory).

CORRECOES APLICADAS (bion.zip original quebrava em runtime nos 3 pontos
abaixo assim que qualquer protocolo fosse executado de fato):

1. `motores/mts.py` instanciava `ResultadoTriagem(..., discriminadores_avaliados=...,
   discriminante_determinante=...)`, mas o dataclass so tinha `cor_mts` e
   `tempo_max_espera`. TypeError certo.

2. `motores/news2.py` instanciava `ResultadoTriagem(nivel_risco_news2=...,
   score_news2=..., subscores_news2=..., alertas=...)` -- nenhum desses
   campos existia no dataclass (nem os do MTS, ja que NEWS2 e um score
   numerico, nao uma cor). TypeError certo.

3. `motores/news2.py` lia `inp.sinais_vitais` em `executar()` e
   `validar_input()`, mas nem `InputTriagem` nem `InputConsulta` tinham
   esse atributo -- so `input_json`. AttributeError certo.

Solucao: os dataclasses de input passaram a expor tanto `input_json`
quanto `sinais_vitais` (lista de dicts com tipo_parametro/valor_numerico,
default vazia). O dataclass de resultado de triagem passou a ser "largo o
suficiente" para os dois protocolos que hoje o usam (MTS = cor; NEWS2 =
score numerico), com todos os campos especificos de cada um opcionais.
Isso evita ter que criar uma hierarquia de subclasses so para dois casos,
mas mantem compatibilidade se um terceiro protocolo de triagem por cor ou
por score for adicionado no futuro.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InputTriagem:
    input_json: dict = field(default_factory=dict)
    sinais_vitais: list = field(default_factory=list)
    queixa_principal: Optional[str] = None


@dataclass
class ResultadoTriagem:
    # Campos genéricos de protocolos de cor (ex.: MTS)
    cor_mts: Optional[str] = None
    tempo_max_espera: Optional[int] = None
    discriminadores_avaliados: list = field(default_factory=list)
    discriminante_determinante: Optional[str] = None
    # Campos genéricos de protocolos de score (ex.: NEWS2)
    nivel_risco_news2: Optional[str] = None
    score_news2: Optional[int] = None
    subscores_news2: dict = field(default_factory=dict)
    # Comum a qualquer protocolo de triagem
    alertas: list = field(default_factory=list)


@dataclass
class InputConsulta:
    input_json: dict = field(default_factory=dict)
    sinais_vitais: list = field(default_factory=list)


@dataclass
class ResultadoConsulta:
    alertas: list = field(default_factory=list)
    indice_confianca: float = 0.0


class IProtocoloTriagem(ABC):
    @abstractmethod
    def executar(self, inp: InputTriagem) -> ResultadoTriagem: ...

    @abstractmethod
    def validar_input(self, i: InputTriagem) -> bool: ...

    @abstractmethod
    def get_nome(self) -> str: ...

    @abstractmethod
    def get_versao(self) -> str: ...


class IProtocoloConsulta(ABC):
    @abstractmethod
    def executar(self, inp: InputConsulta) -> ResultadoConsulta: ...

    @abstractmethod
    def validar_input(self, i: InputConsulta) -> bool: ...

    @abstractmethod
    def get_nome(self) -> str: ...

    @abstractmethod
    def get_versao(self) -> str: ...
