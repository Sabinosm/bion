"""
Schema Pydantic de ENTRADA para alergia e reação alérgica.

Cobre os dois juntos porque adicionar_alergia() cria a alergia E a
primeira reação na mesma chamada (ver Alergia.registrar_reacao) --
mesmo agrupamento que já existia no código antes da divisão.

Os Literal abaixo são cópia manual dos db.Enum de Alergia/ReacaoAlergia
-- não há introspecção automática do schema do banco aqui. Se o Enum
do model mudar, este arquivo precisa ser atualizado junto.

ALTERADO: validação reforçada --
- descricao_reacao/descricao ganharam max_length (estavam sem limite,
  indo texto arbitrariamente grande pro banco).
- strip + rejeição de string vazia/só-espaços em descricao_reacao e
  descricao, mesmo padrão já usado em substancia.
- data_ocorrencia não pode ser no futuro (reação já ocorrida, por
  definição).
- cross-field validator: anafilaxia é por definição uma reação grave
  ou moderada no mínimo -- gravidade="leve" com manifestação
  anafilaxia é inconsistente clinicamente e agora é rejeitado.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

_MANIFESTACOES = Literal["cutanea", "respiratoria", "anafilaxia",
                          "gastrointestinal", "cardiovascular", "sistemica"]
_GRAVIDADES = Literal["leve", "moderada", "grave"]

# Gravidades mínimas aceitáveis por manifestação. Só restringimos o
# caso clinicamente inconsistente conhecido (anafilaxia leve); as
# demais manifestações não têm uma regra de piso tão clara, então
# ficam livres para não sermos mais restritivos do que deveríamos.
_GRAVIDADE_MINIMA_POR_MANIFESTACAO = {
    "anafilaxia": {"moderada", "grave"},
}


def _formatar_erros_pydantic(exc: ValidationError) -> str:
    """Transforma a lista de erros do Pydantic numa mensagem curta,
    uma linha por campo -- consistente com o formato que
    DadosInvalidosError já usava ('Campos obrigatórios ausentes: x, y').
    """
    partes = []
    for erro in exc.errors():
        campo = ".".join(str(p) for p in erro["loc"]) or "(corpo)"
        partes.append(f"{campo}: {erro['msg']}")
    return "; ".join(partes)


def _strip_ou_none(v: Optional[str]) -> Optional[str]:
    """Normaliza campo de texto opcional: string só com espaços vira
    None (em vez de ser salva como lixo "   " no banco); string com
    conteúdo é retornada sem espaços nas pontas."""
    if v is None:
        return None
    v = v.strip()
    return v or None


def _validar_data_nao_futura(v: Optional[date]) -> Optional[date]:
    if v is not None and v > date.today():
        raise ValueError("não pode ser uma data futura")
    return v


class AlergiaCreateSchema(BaseModel):
    substancia: str = Field(min_length=1, max_length=255)
    codigo_substancia: Optional[str] = Field(default=None, max_length=100)
    flag_confirmado: bool = False
    # Campos que viram a PRIMEIRA ReacaoAlergia (ver Alergia.registrar_reacao)
    tipo_reacao: _MANIFESTACOES
    gravidade: _GRAVIDADES
    descricao_reacao: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("substancia")
    @classmethod
    def _substancia_sem_espacos_vazios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("não pode ser vazio ou só espaços")
        return v

    @field_validator("descricao_reacao")
    @classmethod
    def _descricao_reacao_normalizada(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @model_validator(mode="after")
    def _gravidade_compativel_com_manifestacao(self) -> "AlergiaCreateSchema":
        minimas = _GRAVIDADE_MINIMA_POR_MANIFESTACAO.get(self.tipo_reacao)
        if minimas and self.gravidade not in minimas:
            raise ValueError(
                f"gravidade '{self.gravidade}' incompatível com manifestação "
                f"'{self.tipo_reacao}' (esperado: {', '.join(sorted(minimas))})"
            )
        return self


class ReacaoAlergiaCreateSchema(BaseModel):
    manifestacao: _MANIFESTACOES
    gravidade: _GRAVIDADES
    descricao: Optional[str] = Field(default=None, max_length=2000)
    data_ocorrencia: Optional[date] = None

    @field_validator("descricao")
    @classmethod
    def _descricao_normalizada(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("data_ocorrencia")
    @classmethod
    def _data_ocorrencia_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        return _validar_data_nao_futura(v)

    @model_validator(mode="after")
    def _gravidade_compativel_com_manifestacao(self) -> "ReacaoAlergiaCreateSchema":
        minimas = _GRAVIDADE_MINIMA_POR_MANIFESTACAO.get(self.manifestacao)
        if minimas and self.gravidade not in minimas:
            raise ValueError(
                f"gravidade '{self.gravidade}' incompatível com manifestação "
                f"'{self.manifestacao}' (esperado: {', '.join(sorted(minimas))})"
            )
        return self


class AlergiaAtualizarSchema(BaseModel):
    """NOVO: atualização parcial (PATCH-like) da ALERGIA em si -- não
    da reação (isso é ReacaoAlergiaCreateSchema, sem update próprio
    ainda, já que reação é histórico imutável por natureza: uma reação
    registrada errada se corrige removendo e recriando, não editando).

    substancia NÃO é editável de propósito: a alergia já tem um
    histórico de ReacaoAlergia associado a ela; mudar a substância
    deixaria reações antigas (registradas contra a substância
    original) semanticamente presas a um rótulo diferente. Se a
    substância foi cadastrada errada, o caminho é remover a alergia e
    recriar -- não corrigir aqui.
    """
    codigo_substancia: Optional[str] = Field(default=None, max_length=100)
    flag_confirmado: Optional[bool] = None

    @field_validator("codigo_substancia")
    @classmethod
    def _codigo_substancia_normalizado(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    def campos_informados(self) -> dict:
        return self.model_dump(exclude_unset=True)