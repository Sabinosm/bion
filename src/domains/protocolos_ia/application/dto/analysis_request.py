"""Este arquivo define a fronteira de entrada do módulo: o corpo HTTP de /analisar-llm é validado e normalizado aqui.

Compatibilidade: aceita medicamentos_em_uso como sinônimo de medicamentos (valores divergentes são rejeitados),
sexo_biologico opcional (ausente vira nao_informado) e id_input_protocolo opcional.
Com id_input_protocolo, o contexto clínico vem do snapshot do servidor e os campos clínicos do corpo são ignorados.
Sem id_input_protocolo, a análise é avulsa e nada é persistido.
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.core.exceptions import DadosInvalidosError

from ...domain.strategies.registro import TIPO_PADRAO

LIMITE_LISTA = 50
CAMPOS_CLINICOS = (
    "sexo_biologico", "data_nascimento", "sinais_vitais", "alergias", "doencas", "medicamentos",
    "queixa_principal", "resultado_triagem", "tipo_sanguineo", "secoes_negadas",
)


class LLMAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tipo_analise: str = Field(default=TIPO_PADRAO, min_length=1, max_length=50)
    id_input_protocolo: Optional[int] = Field(default=None, ge=1)
    sexo_biologico: Optional[str] = Field(default=None, max_length=1)
    data_nascimento: Optional[str] = Field(default=None, max_length=10)
    sinais_vitais: Optional[List[Any]] = Field(default=None, max_length=LIMITE_LISTA)
    alergias: Optional[List[Any]] = Field(default=None, max_length=LIMITE_LISTA)
    doencas: Optional[List[Any]] = Field(default=None, max_length=LIMITE_LISTA)
    medicamentos: Optional[List[Any]] = Field(default=None, max_length=LIMITE_LISTA)
    queixa_principal: Optional[str] = Field(default=None, max_length=1000)
    resultado_triagem: Optional[dict] = None
    tipo_sanguineo: Optional[str] = Field(default=None, max_length=3)
    secoes_negadas: List[Literal["alergias", "doencas", "medicamentos"]] = Field(default_factory=list, max_length=3)

    @field_validator("id_input_protocolo", mode="before")
    @classmethod
    def sem_booleano(cls, v):
        if isinstance(v, bool):
            raise ValueError("id_input_protocolo deve ser um inteiro.")
        return v

    @property
    def vinculada(self) -> bool:
        return self.id_input_protocolo is not None

    @classmethod
    def de_corpo_http(cls, corpo: Any) -> "LLMAnalysisRequest":
        """Esta função valida o corpo JSON. Erros listam campo e motivo, nunca o valor recebido."""
        if corpo is None:
            corpo = {}
        if not isinstance(corpo, dict):
            raise DadosInvalidosError("O corpo da requisição deve ser um objeto JSON.", campo="_geral")
        dados = dict(corpo)
        if "medicamentos_em_uso" in dados:
            alias = dados.pop("medicamentos_em_uso")
            if "medicamentos" in dados and dados["medicamentos"] != alias:
                raise DadosInvalidosError(
                    "medicamentos e medicamentos_em_uso divergem; envie apenas um deles.", campo="medicamentos"
                )
            dados["medicamentos"] = alias
        try:
            return cls.model_validate(dados)
        except ValidationError as exc:
            erros = {}
            for e in exc.errors():
                campo = ".".join(str(p) for p in e["loc"]) or "_geral"
                erros.setdefault(campo, e["msg"])
            raise DadosInvalidosError("Dados inválidos na requisição.", erros=erros) from None

    def dados_clinicos(self) -> dict:
        """Esta função devolve os argumentos de contexto_de_dados_avulsos."""
        return {
            "sexo_biologico": self.sexo_biologico,
            "data_nascimento": self.data_nascimento,
            "sinais_vitais": self.sinais_vitais,
            "alergias": self.alergias,
            "doencas": self.doencas,
            "medicamentos": self.medicamentos,
            "queixa_principal": self.queixa_principal,
            "resultado_triagem": self.resultado_triagem,
            "tipo_sanguineo": self.tipo_sanguineo,
            "secoes_negadas": self.secoes_negadas,
        }
