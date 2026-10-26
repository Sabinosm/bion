"""Contrato clínico da resposta da LLM. Este é o único formato aceito e persistido pelo módulo."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISCLAIMER_CLINICO = (
    "Esta análise é gerada por inteligência artificial como apoio à decisão clínica. "
    "A decisão diagnóstica e terapêutica final é exclusivamente do profissional de saúde habilitado."
)


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HipoteseDiagnostica(_Estrito):
    descricao: str = Field(..., min_length=3, max_length=300)
    codigo_cid10: Optional[str] = Field(None, pattern=r"^[A-Z]\d{2}(\.\d{1,2})?$")
    probabilidade: Literal["alta", "moderada", "baixa"] = "moderada"
    dados_que_suportam: List[str] = Field(default_factory=list, max_length=10)
    dados_que_contradizem: List[str] = Field(default_factory=list, max_length=10)

    @field_validator("descricao")
    @classmethod
    def descricao_nao_vazia(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Descrição da hipótese não pode estar vazia.")
        return v

    @field_validator("dados_que_suportam", "dados_que_contradizem")
    @classmethod
    def itens_curtos(cls, v: List[str]) -> List[str]:
        if any(len(x) > 300 for x in v):
            raise ValueError("Item de evidência acima do tamanho permitido.")
        return v


class ExameSugerido(_Estrito):
    nome: str = Field(..., min_length=2, max_length=200)
    justificativa: Optional[str] = Field(None, max_length=500)


class MedicamentoSugerido(_Estrito):
    """Sugestão de princípio ativo. Não contém dose, via, duração nem posologia: não é prescrição."""

    principio_ativo: str = Field(..., min_length=2, max_length=200)
    justificativa: Optional[str] = Field(None, max_length=500)


class RespostaLLM(_Estrito):
    resumo_clinico: str = Field(..., min_length=50, max_length=3000)
    hipoteses_diagnosticas: List[HipoteseDiagnostica] = Field(default_factory=list, max_length=5)
    alertas: List[str] = Field(default_factory=list, max_length=10)
    exames_sugeridos: List[ExameSugerido] = Field(default_factory=list, max_length=10)
    medicamentos_sugeridos: List[MedicamentoSugerido] = Field(default_factory=list, max_length=10)
    explicacao_divergencia: Optional[str] = Field(None, max_length=1000)
    disclaimer_clinico: str = DISCLAIMER_CLINICO

    @field_validator("resumo_clinico", mode="before")
    @classmethod
    def resumo_nao_vazio(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Campo de texto não pode estar vazio.")
        return v

    @field_validator("alertas", mode="before")
    @classmethod
    def alertas_como_lista(cls, v):
        """Aceita uma string única como lista de um item. Qualquer outro tipo não lista é rejeitado."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if not isinstance(v, list):
            raise ValueError("alertas deve ser uma lista de strings.")
        return v

    @field_validator("alertas")
    @classmethod
    def alertas_curtos(cls, v: List[str]) -> List[str]:
        if any(len(x) > 500 for x in v):
            raise ValueError("Alerta acima do tamanho permitido.")
        return v

    @field_validator("disclaimer_clinico", mode="before")
    @classmethod
    def disclaimer_definido_pelo_servidor(cls, _v):
        """O aviso clínico é fixo e definido pelo servidor, independente do que o modelo devolver."""
        return DISCLAIMER_CLINICO

    def para_dict_persistencia(self) -> dict:
        return self.model_dump(mode="json", exclude_none=False)
