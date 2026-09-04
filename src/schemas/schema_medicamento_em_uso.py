"""
Schema Pydantic de ENTRADA para medicamento em uso.

O Literal de `status_uso` é cópia manual do db.Enum de
MedicamentoEmUso -- não há introspecção automática do schema do banco
aqui. Se o Enum do model mudar, este arquivo precisa ser atualizado
junto.

Checagem de que id_catalogo EXISTE em catalogo_medicamentos não entra
aqui -- é uma FK, não formato, então fica no service (query real
contra o banco), não no schema.

ALTERADO: validação reforçada --
- descricao ganhou max_length (estava sem limite); descricao/dose/
  frequencia ganharam strip + rejeição de string vazia/só-espaços.
- desde não pode ser uma data futura.
- cross-field validator: quando status_uso vem explícito junto com
  flag_em_uso, os dois precisam ser coerentes (ex: flag_em_uso=False
  com status_uso="ativo" é contraditório). Quando status_uso não vem,
  a derivação automática a partir de flag_em_uso é mantida como antes.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# status_uso que são coerentes com cada valor de flag_em_uso. Usado só
# para rejeitar combinações claramente contraditórias quando AMBOS os
# campos vêm explícitos no payload -- não para inventar regra nova
# além da derivação que já existia no service.
_STATUS_COERENTES_COM_FLAG = {
    True: {"ativo"},
    False: {"interrompido", "concluido"},
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


def _validar_texto_obrigatorio(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("não pode ser vazio ou só espaços")
    return v


def _strip_ou_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    return v or None


class MedicamentoEmUsoCreateSchema(BaseModel):
    id_catalogo: int = Field(gt=0)
    descricao: str = Field(min_length=1, max_length=2000)
    dose: Optional[str] = Field(default=None, max_length=100)
    frequencia: Optional[str] = Field(default=None, max_length=100)
    desde: Optional[date] = None
    flag_em_uso: bool = True
    status_uso: Optional[Literal["ativo", "interrompido", "concluido"]] = None

    @field_validator("descricao")
    @classmethod
    def _descricao_sem_espacos_vazios(cls, v: str) -> str:
        return _validar_texto_obrigatorio(v)

    @field_validator("dose", "frequencia")
    @classmethod
    def _normalizado(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("desde")
    @classmethod
    def _desde_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("não pode ser uma data futura")
        return v

    @field_validator("status_uso")
    @classmethod
    def _default_conforme_flag(cls, v, info):
        # Reproduz a regra que já existia no service: se status_uso não
        # vier, deriva de flag_em_uso -- mantido aqui para não perder
        # esse comportamento ao migrar a validação pro schema.
        if v is not None:
            return v
        flag = info.data.get("flag_em_uso", True)
        return "ativo" if flag else "interrompido"

    @model_validator(mode="after")
    def _status_coerente_com_flag(self) -> "MedicamentoEmUsoCreateSchema":
        # Neste ponto status_uso NUNCA é None (o field_validator acima
        # sempre deriva um valor) -- então esta checagem só pega o caso
        # em que o valor vindo explícito do payload contradiz flag_em_uso.
        coerentes = _STATUS_COERENTES_COM_FLAG[self.flag_em_uso]
        if self.status_uso not in coerentes:
            raise ValueError(
                f"status_uso '{self.status_uso}' incompatível com "
                f"flag_em_uso={self.flag_em_uso} (esperado: {', '.join(sorted(coerentes))})"
            )
        return self


class MedicamentoEmUsoAtualizarSchema(BaseModel):
    """NOVO: atualização parcial (PATCH-like) -- todo campo é opcional.

    id_catalogo NÃO é editável de propósito: trocar de medicamento é
    conceitualmente um novo registro (nova prescrição), não uma
    correção do existente -- diferente de dose/frequencia/status_uso,
    que mudam ao longo do tratamento do mesmo medicamento. Se o
    catálogo estiver errado, o caminho é remover e recadastrar, não
    editar aqui.
    """
    descricao: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    dose: Optional[str] = Field(default=None, max_length=100)
    frequencia: Optional[str] = Field(default=None, max_length=100)
    desde: Optional[date] = None
    flag_em_uso: Optional[bool] = None
    status_uso: Optional[Literal["ativo", "interrompido", "concluido"]] = None

    @field_validator("descricao")
    @classmethod
    def _descricao_sem_espacos_vazios(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validar_texto_obrigatorio(v)

    @field_validator("dose", "frequencia")
    @classmethod
    def _normalizado(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @field_validator("desde")
    @classmethod
    def _desde_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("não pode ser uma data futura")
        return v

    @model_validator(mode="after")
    def _status_coerente_com_flag_se_ambos_vierem(self) -> "MedicamentoEmUsoAtualizarSchema":
        # Diferente do Create, aqui os dois campos são opcionais e não
        # há derivação automática -- só validamos coerência quando AMBOS
        # vêm no payload de atualização. Se só um vier, não temos como
        # saber o valor atual do outro (isso é responsabilidade do
        # service, que já tem o registro carregado).
        if self.flag_em_uso is not None and self.status_uso is not None:
            coerentes = _STATUS_COERENTES_COM_FLAG[self.flag_em_uso]
            if self.status_uso not in coerentes:
                raise ValueError(
                    f"status_uso '{self.status_uso}' incompatível com "
                    f"flag_em_uso={self.flag_em_uso} (esperado: {', '.join(sorted(coerentes))})"
                )
        return self

    def campos_informados(self) -> dict:
        return self.model_dump(exclude_unset=True)


class MedicamentoEmUsoRemoverSchema(BaseModel):
    """NOVO: schema de entrada para o soft delete (DELETE) de um
    medicamento em uso -- mesmo padrão de AlergiaRemoverSchema/
    DoencaCronicaRemoverSchema. motivo é obrigatório;
    motivo_delete='outro' exige observacoes_delete preenchida (não
    vazia/só-espaços)."""
    motivo_delete: Literal[
        "erro-digitacao",
        "registro-duplicado",
        "diagnostico-incorreto",
        "solicitacao-paciente",
        "outro",
    ]
    observacoes_delete: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("observacoes_delete")
    @classmethod
    def _observacoes_delete_normalizadas(cls, v: Optional[str]) -> Optional[str]:
        return _strip_ou_none(v)

    @model_validator(mode="after")
    def _outro_exige_observacao(self) -> "MedicamentoEmUsoRemoverSchema":
        if self.motivo_delete == "outro" and not self.observacoes_delete:
            raise ValueError(
                "observacoes_delete é obrigatória e não pode ser vazia "
                "quando motivo_delete='outro'"
            )
        return self