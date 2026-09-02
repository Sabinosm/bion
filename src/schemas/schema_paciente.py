"""
Schema Pydantic de ENTRADA para atualização de Paciente -- pessoal e
clínico, refletindo a mesma separação de PacienteService.
atualizar_pessoal / atualizar_clinico.

Ambos são schemas de ATUALIZAÇÃO PARCIAL (tipo PATCH): todo campo é
opcional -- só o que vier no payload é validado e aplicado. Isso é
diferente dos schemas de criação (*CreateSchema em outros domínios),
onde campo ausente é erro.

O Literal de `status` é cópia manual do db.Enum de Paciente -- não há
introspecção automática do schema do banco aqui. Se o Enum do model
mudar, este arquivo precisa ser atualizado junto.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator, model_validator


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


class PacienteAtualizarPessoalSchema(BaseModel):
    """Todos os campos são opcionais -- só o que vier é atualizado
    (ver PacienteService.atualizar_pessoal, que já faz `if campo in
    dados`). Aqui só entra validação de FORMATO para o que for
    enviado; campo ausente nunca é erro.
    """
    nome_completo: Optional[str] = Field(default=None, min_length=1, max_length=500)
    telefone: Optional[str] = Field(default=None, min_length=8, max_length=20)
    email: Optional[EmailStr] = None
    logradouro: Optional[str] = Field(default=None, min_length=1, max_length=500)
    cep: Optional[str] = Field(default=None, min_length=8, max_length=9)
    contato_emergencia_telefone: Optional[str] = Field(default=None, min_length=8, max_length=20)
    rg: Optional[str] = Field(default=None, max_length=100)
    numero_residencia: Optional[str] = Field(default=None, max_length=50)
    contato_emergencia_nome: Optional[str] = Field(default=None, max_length=255)

    @field_validator("nome_completo", "logradouro")
    @classmethod
    def _nao_pode_ser_so_espacos(cls, v):
        if v is not None and not v.strip():
            raise ValueError("não pode ser vazio ou só espaços")
        return v

    @field_validator("cep")
    @classmethod
    def _cep_so_digitos(cls, v):
        if v is not None and not v.replace("-", "").isdigit():
            raise ValueError("deve conter apenas dígitos (com ou sem hífen)")
        return v

    def campos_informados(self) -> dict:
        """Só os campos que vieram de fato no payload (exclui os que
        ficaram None por serem opcionais e ausentes) -- para o service
        aplicar apenas o que foi enviado, igual o `if campo in dados`
        original fazia antes de existir schema."""
        return self.model_dump(exclude_none=True, exclude_unset=True)


class PacienteAtualizarClinicoSchema(BaseModel):
    """Idem: PATCH parcial. status agora é Literal (antes aceitava
    qualquer string, só falhava no commit() como IntegrityError cru).

    Regra de consistência (decisão confirmada): falecido=True FORÇA
    status="obito" automaticamente -- não é uma via de mão dupla. Não
    exigimos data_obito nem o inverso (status="obito" não obriga
    falecido=True nem data_obito) -- ficar rígido demais aqui não foi
    o que se pediu; só a direção falecido->status é garantida.
    """
    status: Optional[Literal["ativo", "inativo", "obito"]] = None
    falecido: Optional[bool] = None
    data_obito: Optional[date] = None

    @model_validator(mode="after")
    def _falecido_forca_status_obito(self):
        if self.falecido is True:
            self.status = "obito"
        return self

    def campos_informados(self) -> dict:
        return self.model_dump(exclude_none=True, exclude_unset=False)