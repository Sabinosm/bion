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

ALTERADO: validação reforçada --
- telefone/contato_emergencia_telefone agora usam validar_telefone_br
  (DDD real, dígito 9 no celular, rejeita sequência repetida) em vez
  de só checar tamanho -- "abcdefgh" ou "00011112222" passavam antes.
- cep agora usa validar_e_devolver_cep (8 dígitos de verdade, rejeita
  sequência tipo "11111111") em vez de só validar "8-9 caracteres";
  o valor é normalizado para só-dígitos no schema, já que é isso que
  validar_e_devolver_cep devolve.
- rg, numero_residencia, contato_emergencia_nome ganharam strip +
  rejeição de string vazia/só-espaços.
- data_obito não aceita mais data futura.

Import de src.core.validacoes deixado como está -- ajuste de path é
por conta de quem for integrar.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator, model_validator

from src.core.validacoes import validar_e_devolver_cep, validar_telefone_br


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
    if v is None:
        return None
    v = v.strip()
    return v or None


class PacienteAtualizarPessoalSchema(BaseModel):
    """Todos os campos são opcionais -- só o que vier é atualizado
    (ver PacienteService.atualizar_pessoal, que já faz `if campo in
    dados`). Aqui só entra validação de FORMATO para o que for
    enviado; campo ausente nunca é erro.
    """
    nome_completo: Optional[str] = Field(default=None, min_length=1, max_length=500)
    telefone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[EmailStr] = None
    logradouro: Optional[str] = Field(default=None, min_length=1, max_length=500)
    cep: Optional[str] = Field(default=None, max_length=9)
    contato_emergencia_telefone: Optional[str] = Field(default=None, max_length=20)
    rg: Optional[str] = Field(default=None, max_length=100)
    numero_residencia: Optional[str] = Field(default=None, max_length=50)
    contato_emergencia_nome: Optional[str] = Field(default=None, max_length=255)

    @field_validator("nome_completo", "logradouro")
    @classmethod
    def _nao_pode_ser_so_espacos(cls, v):
        if v is not None and not v.strip():
            raise ValueError("não pode ser vazio ou só espaços")
        return v

    @field_validator("rg", "numero_residencia", "contato_emergencia_nome")
    @classmethod
    def _normalizado(cls, v):
        return _strip_ou_none(v)

    @field_validator("telefone", "contato_emergencia_telefone")
    @classmethod
    def _telefone_valido(cls, v):
        if v is None:
            return None
        if not validar_telefone_br(v):
            raise ValueError("telefone inválido (DDD ou formato incorreto)")
        return v

    @field_validator("cep")
    @classmethod
    def _cep_valido(cls, v):
        if v is None:
            return None
        cep_normalizado = validar_e_devolver_cep(v)
        if cep_normalizado is None:
            raise ValueError("CEP inválido")
        return cep_normalizado

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

    @field_validator("data_obito")
    @classmethod
    def _data_obito_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("não pode ser uma data futura")
        return v

    @model_validator(mode="after")
    def _falecido_forca_status_obito(self):
        if self.falecido is True:
            self.status = "obito"
        return self

    def campos_informados(self) -> dict:
        return self.model_dump(exclude_none=True, exclude_unset=False)