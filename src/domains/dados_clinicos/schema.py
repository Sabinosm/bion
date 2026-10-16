"""Schemas de entrada do registro de dados clínicos (sinais vitais e coleta clínica).

Os valores dos enums abaixo espelham os do model SinalVital: se o model
mudar, mude aqui também. Valor fora do enum vira 422 aqui, em vez de
estourar como erro do banco no commit.

SINAIS VITAIS: payload {"sinais": [ {...}, ... ]}, de 1 a 50 itens.
  - tipo_parametro, valor_numerico e unidade são obrigatórios.
  - a unidade precisa corresponder ao tipo (temperatura = °C, spo2 = %, ...).
  - flag_validacao_faixa e flag_escala_dpoc seguem opcionais, com os mesmos
    padrões de antes.

COLETA CLÍNICA: desde_quando_sintomas (horas), opcional, inteiro 0..32767.

INPUT DE PROTOCOLO: valida só o ENVELOPE. O conteúdo de `input_json` é livre
(um objeto JSON qualquer) até existir um schema para ele.
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TipoParametro = Literal[
    "frequencia-respiratoria", "spo2", "pa-sistolica", "pa-diastolica",
    "frequencia-cardiaca", "temperatura", "glicemia-capilar",
]
Unidade = Literal["irpm", "%", "mmHg", "bpm", "°C", "mg-dL"]
SitioMedicao = Literal[
    "axilar", "oral", "retal", "timpanico", "oximetria-digital",
    "manguito-braco-direito", "manguito-braco-esquerdo",
]
FlagFaixa = Literal["dentro-do-limite", "fora-limite-alertado", "fora-limite-rejeitado"]

UNIDADE_POR_TIPO = {
    "frequencia-respiratoria": "irpm",
    "spo2": "%",
    "pa-sistolica": "mmHg",
    "pa-diastolica": "mmHg",
    "frequencia-cardiaca": "bpm",
    "temperatura": "°C",
    "glicemia-capilar": "mg-dL",
}


def _sem_bool(v):
    """bool é int em Python: True viraria 1 sem reclamar."""
    if isinstance(v, bool):
        raise ValueError("deve ser numérico, não booleano")
    return v


class SinalVitalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_parametro: TipoParametro
    valor_numerico: float = Field(ge=0, le=99999999.99, allow_inf_nan=False)
    unidade: Unidade
    sitio_medicao: Optional[SitioMedicao] = None
    flag_validacao_faixa: FlagFaixa = "dentro-do-limite"
    flag_escala_dpoc: bool = False

    _v_valor = field_validator("valor_numerico", mode="before")(_sem_bool)

    @model_validator(mode="after")
    def _unidade_confere_com_o_tipo(self):
        esperada = UNIDADE_POR_TIPO[self.tipo_parametro]
        if self.unidade != esperada:
            raise ValueError(
                f"unidade '{self.unidade}' não corresponde a '{self.tipo_parametro}' (esperado: {esperada})"
            )
        return self


class SinaisVitaisIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sinais: List[SinalVitalIn] = Field(min_length=1, max_length=50)


class ColetaClinicaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desde_quando_sintomas: Optional[int] = Field(default=None, ge=0, le=32767)

    _v_horas = field_validator("desde_quando_sintomas", mode="before")(_sem_bool)


TipoInput = Literal["triagem", "avaliacao-medica"]


class InputProtocoloIn(BaseModel):
    """Envelope do input de protocolo. `tipo_input` é opcional: o padrão é o
    tipo do próprio atendimento (e, se vier, tem de ser igual a ele; a
    checagem é do service). Exige ao menos um campo de conteúdo."""
    model_config = ConfigDict(extra="forbid")

    tipo_input: Optional[TipoInput] = None
    input_json: Optional[dict] = None
    queixa_principal: Optional[str] = Field(default=None, max_length=2000)
    valor_avpu: Optional[str] = Field(default=None, max_length=20)
    dados_criticos_ausentes: Optional[Union[list, dict]] = None

    @field_validator("queixa_principal", "valor_avpu", mode="before")
    @classmethod
    def _texto(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("deve ser texto")
        return v.strip() or None

    @model_validator(mode="after")
    def _algum_conteudo(self):
        if not any((self.input_json, self.queixa_principal, self.valor_avpu,
                    self.dados_criticos_ausentes)):
            raise ValueError(
                "informe ao menos um de: input_json, queixa_principal, valor_avpu, "
                "dados_criticos_ausentes"
            )
        return self