"""Schemas Pydantic (v2) da prescrição.

Médico (rotas HTTP) e IA (resposta do modelo) validam com as MESMAS classes.

extra="forbid": qualquer campo fora do contrato (origem_sugestao, id_output_origem,
id_resultado, status, formulado_por...) vira erro de validação em vez de ser ignorado.
Os schemas validam FORMA; a existência dos ids nos catálogos é checada no service.
"""

from typing import Annotated, Literal, Optional

from pydantic import (
    BaseModel, ConfigDict, Field, StrictInt, StringConstraints,
    ValidationError, field_validator, model_validator,
)

Texto100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Texto255 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Texto2000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
IdPositivo = Annotated[StrictInt, Field(gt=0)]  # rejeita "12" e true
# CID-10: letra + 2 dígitos, subcategoria opcional (A90, J45.9, S72.01)
CodigoCid10 = Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{2}(\.[0-9]{1,2})?$")]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _vazio_vira_none(cls, v):
        """Campo de texto em branco (comum em formulário) é tratado como ausente."""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class ResultadoPrescricaoIn(_Base):
    """Diagnóstico + categoria da prescrição. consistente_com_classificacao, status,
    formulado_por e id_output NÃO entram aqui: são definidos pelo servidor."""
    codigo_cid10_principal: CodigoCid10
    descricao_cid10_principal: Texto255
    certeza_diagnostica: Literal["suspeito", "provavel", "confirmado", "descartado"]
    tipo_prescricao: Optional[Literal[
        "farmacologica", "nao-farmacologica", "encaminhamento", "internacao", "alta"
    ]] = None

    @field_validator("codigo_cid10_principal", mode="before")
    @classmethod
    def _cid_maiusculo(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class MedicamentoPrescritoIn(_Base):
    id_catalogo: IdPositivo
    dose: Optional[Texto100] = None
    frequencia: Optional[Texto100] = None
    duracao: Optional[Texto100] = None
    orientacoes: Optional[Texto2000] = None


class ExamePrescritoIn(_Base):
    id_exame: IdPositivo
    urgencia: Literal["rotina", "urgente", "emergencia"] = "rotina"
    justificativa: Optional[Texto2000] = None


class PropostaPrescricaoIA(_Base):
    """Formato exigido da resposta da IA.

    Sem medicamentos e sem exames = sem recomendação: isso fica registrado no
    Output_bion e NÃO gera ResultadoPrescricao."""
    resultado: Optional[ResultadoPrescricaoIn] = None
    medicamentos: list[MedicamentoPrescritoIn] = Field(default_factory=list, max_length=20)
    exames: list[ExamePrescritoIn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _consistente(self):
        ids_med = [m.id_catalogo for m in self.medicamentos]
        ids_exa = [e.id_exame for e in self.exames]
        if len(ids_med) != len(set(ids_med)) or len(ids_exa) != len(set(ids_exa)):
            raise ValueError("Itens repetidos na prescrição.")
        if (self.medicamentos or self.exames) and self.resultado is None:
            raise ValueError("'resultado' (CID-10 e certeza diagnóstica) é obrigatório quando há itens.")
        return self

    @property
    def sem_recomendacao(self) -> bool:
        return not self.medicamentos and not self.exames


def formatar_erros_pydantic(ex: ValidationError) -> str:
    """Texto curto para json_error. Troque pelo helper compartilhado do projeto, se preferir."""
    partes = []
    for e in ex.errors():
        campo = ".".join(str(p) for p in e["loc"]) or "body"
        partes.append(f"{campo}: {e['msg']}")
    return "; ".join(partes)