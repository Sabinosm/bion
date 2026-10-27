"""Schemas Pydantic (v2) da prescrição.

Médico (rotas HTTP) e IA (resposta do modelo) validam com as MESMAS classes.

extra="forbid": qualquer campo fora do contrato (origem_sugestao, id_output_origem,
id_resultado, status, formulado_por...) vira erro de validação em vez de ser ignorado.
Os schemas validam FORMA; a existência dos itens nos catálogos é checada no service.

Catálogos são referenciados pelo UUID público (é o que o to_dict() deles expõe),
nunca pelo id numérico interno.
"""

from typing import Annotated, Literal, Optional

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StringConstraints,
    ValidationError, field_validator, model_validator,
)

Texto100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Texto255 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Texto2000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
UuidStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    ),
    AfterValidator(str.lower),
]
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
    uuid_catalogo: UuidStr  # uuid de CatalogoMedicamentos
    dose: Optional[Texto100] = None
    frequencia: Optional[Texto100] = None
    duracao: Optional[Texto100] = None
    orientacoes: Optional[Texto2000] = None


class ExamePrescritoIn(_Base):
    uuid_exame: UuidStr  # uuid de CatalogoExames (catálogo ainda a planejar)
    urgencia: Literal["rotina", "urgente", "emergencia"] = "rotina"
    justificativa: Optional[Texto2000] = None


_CERTEZAS = Literal["suspeito", "provavel", "confirmado", "descartado"]
_TIPOS_PRESCRICAO = Literal["farmacologica", "nao-farmacologica", "encaminhamento", "internacao", "alta"]


class ResultadoPrescricaoPatch(_Base):
    """PATCH do diagnóstico do rascunho: só os campos enviados mudam. tipo_prescricao pode ser
    limpo com null; os demais são obrigatórios no model, então null neles é erro."""
    codigo_cid10_principal: Optional[CodigoCid10] = None
    descricao_cid10_principal: Optional[Texto255] = None
    certeza_diagnostica: Optional[_CERTEZAS] = None
    tipo_prescricao: Optional[_TIPOS_PRESCRICAO] = None

    @field_validator("codigo_cid10_principal", mode="before")
    @classmethod
    def _cid_maiusculo(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _ao_menos_um(self):
        enviados = self.model_fields_set
        if not enviados:
            raise ValueError("Informe ao menos um campo para alterar.")
        for campo in ("codigo_cid10_principal", "descricao_cid10_principal", "certeza_diagnostica"):
            if campo in enviados and getattr(self, campo) is None:
                raise ValueError(f"'{campo}' não pode ser vazio.")
        return self


class MedicamentoPrescritoPatch(_Base):
    """PATCH de um medicamento do rascunho: dose, frequência, duração e orientações (null/vazio limpa).
    Trocar o medicamento é remover e adicionar outro."""
    dose: Optional[Texto100] = None
    frequencia: Optional[Texto100] = None
    duracao: Optional[Texto100] = None
    orientacoes: Optional[Texto2000] = None

    @model_validator(mode="after")
    def _ao_menos_um(self):
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        return self


class ExamePrescritoPatch(_Base):
    """PATCH de um exame do rascunho: urgência (não aceita null) e justificativa (null/vazio limpa)."""
    urgencia: Optional[Literal["rotina", "urgente", "emergencia"]] = None
    justificativa: Optional[Texto2000] = None

    @model_validator(mode="after")
    def _ao_menos_um(self):
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        if "urgencia" in self.model_fields_set and self.urgencia is None:
            raise ValueError("'urgencia' não pode ser vazia.")
        return self


class DescartarPrescricaoIn(_Base):
    """Corpo (opcional) de POST /<uuid_resultado>/descartar."""
    motivo: Optional[Texto255] = None


class ConfirmacaoPrescricaoIn(_Base):
    """Corpo de POST /<uuid_resultado>/confirmar."""
    reconhecer_alertas: StrictBool = False


class PropostaPrescricaoIA(_Base):
    """Formato exigido da resposta da IA.

    Sem medicamentos e sem exames = sem recomendação: isso fica registrado no
    Output_bion e NÃO gera ResultadoPrescricao."""
    resultado: Optional[ResultadoPrescricaoIn] = None
    medicamentos: list[MedicamentoPrescritoIn] = Field(default_factory=list, max_length=20)
    exames: list[ExamePrescritoIn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _consistente(self):
        uuids_med = [m.uuid_catalogo for m in self.medicamentos]
        uuids_exa = [e.uuid_exame for e in self.exames]
        if len(uuids_med) != len(set(uuids_med)) or len(uuids_exa) != len(set(uuids_exa)):
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