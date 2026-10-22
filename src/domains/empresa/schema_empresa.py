"""
schema_empresa.py

Schemas Pydantic de ENTRADA do domínio Empresa: um para o cadastro, em que os
campos obrigatórios continuam obrigatórios, e outro para a atualização
parcial. Normalizam e validam o payload (CNPJ, CNES e CEP ficam só com
dígitos, campos em branco do DPO viram nulos, o endereço aninhado enviado pelo
front é achatado) e rejeitam qualquer campo não previsto, o que impede o
cliente de enviar dados que ele não pode definir ou alterar. Não consultam o
banco nem aplicam regras que dependam de outros registros; isso fica no
service.
"""

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from src.core import validacoes as vl
from src.core.erros_pydantic import erros_pydantic_por_campo  # noqa: F401 (mantido para imports legados)


REGEX_CEP_LIMPO = re.compile(r"^\d{8}$")
REGEX_NUMERO_ENDERECO = re.compile(r"^[A-Za-z0-9°ºª\s\-/.,]{1,10}$")
STATUS_PLANO_VALIDOS = {"ativo", "inativo", "suspenso", "cancelado"}


def _normalizar_cnes(v: Optional[str]) -> Optional[str]:
    """Vazio vira None; caso contrário mantém só dígitos e exige 7."""
    if v is None or v == "":
        return None
    v = re.sub(r"\D", "", v)
    if len(v) != 7:
        raise ValueError("CNES deve conter 7 dígitos.")
    return v


def _normalizar_cep(v: Optional[str]) -> Optional[str]:
    """Vazio vira None; caso contrário valida o CEP e devolve só os dígitos."""
    if v is None or v == "":
        return None
    if not vl.validar_cep(v):
        raise ValueError("CEP inválido.")
    return re.sub(r"\D", "", v)


def _normalizar_numero(v: Optional[str]) -> Optional[str]:
    """Vazio vira None; caso contrário valida os caracteres permitidos do número do endereço."""
    if v is None or v == "":
        return None
    v = v.strip()
    if not REGEX_NUMERO_ENDERECO.match(v):
        raise ValueError("Número do endereço contém caracteres inválidos.")
    return v


def _vazio_para_none(v):
    """Texto vazio ou só com espaços vira None; qualquer outro valor passa direto."""
    if isinstance(v, str) and not v.strip():
        return None
    return v


class CadastroEmpresaSchema(BaseModel):
    """Payload de criação da empresa. Exige ao menos CNPJ ou CNES."""

    # Tamanhos alinhados com o model Empresa (255/255/150) e com o front.
    nome_fantasia: str = Field(..., min_length=2, max_length=255)
    razao_social: Optional[str] = Field(None, max_length=255)
    cnpj: Optional[str] = None
    cnes: Optional[str] = Field(None, max_length=20)
    numero: Optional[str] = Field(None, max_length=10)
    bairro: Optional[str] = Field(None, max_length=100)
    complemento: Optional[str] = Field(None, max_length=150)
    cep: Optional[str] = None
    status_plano: str = "ativo"
    plano: Optional[str] = None
    dpo_nome: Optional[str] = Field(None, max_length=255)
    dpo_email: Optional[EmailStr] = Field(None, max_length=255)

    model_config = {
        "str_strip_whitespace": True,
        "extra": "forbid",
    }

    @field_validator("cnpj")
    @classmethod
    def valida_e_limpa_cnpj(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not vl.validar_cnpj(v):
            raise ValueError("O CNPJ está incorreto.")
        return re.sub(r"\D", "", v)

    @field_validator("cnes")
    @classmethod
    def valida_cnes(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_cnes(v)

    @field_validator("cep")
    @classmethod
    def valida_cep(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_cep(v)

    @field_validator("dpo_nome", "dpo_email", mode="before")
    @classmethod
    def dpo_vazio_vira_none(cls, v):
        """"" ou só espaços viram None (EmailStr rejeitaria ""). Sem DPO, o
        service usa nome e e-mail do admin que está sendo criado."""
        return _vazio_para_none(v)

    @field_validator("numero")
    @classmethod
    def valida_numero(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_numero(v)

    @field_validator("status_plano")
    @classmethod
    def valida_status_plano(cls, v: str) -> str:
        if v not in STATUS_PLANO_VALIDOS:
            raise ValueError(f"status_plano deve ser um de: {', '.join(sorted(STATUS_PLANO_VALIDOS))}.")
        return v

    @model_validator(mode="after")
    def exige_cnpj_ou_cnes(self):
        if not self.cnpj and not self.cnes:
            raise ValueError("Informe o CNPJ ou o CNES.")
        return self


class AtualizacaoEmpresaSchema(BaseModel):
    """Atualização parcial da empresa, só com campos AUTOGERENCIÁVEIS.

    São os dados cadastrais comuns que a própria empresa pode alterar, sem
    implicação legal ou financeira. O CNES entra aqui, mas não é coluna de
    Empresa (é um registro em EmpresaIdentificador): o schema valida só o
    formato e o service grava via empresa.definir_cnes(), nunca por setattr.

    Ficam de fora, e `extra: forbid` rejeita se enviados:
    - CNPJ: fixo após o cadastro (mudança exige alteração na Receita).
    - Campos RESTRITOS (ex.: status_plano, plano): ninguém altera por este
      schema, pois o Bion ainda não tem um papel "admin Bion" separado do
      admin cliente. Quando existir, devem migrar para uma rota própria desse
      papel, já que a empresa não pode se autoconceder, por exemplo, a
      reativação do próprio plano suspenso.
    """

    nome_fantasia: Optional[str] = Field(None, min_length=2, max_length=255)
    cnes: Optional[str] = Field(None, max_length=20)
    numero: Optional[str] = Field(None, max_length=10)
    bairro: Optional[str] = Field(None, max_length=100)
    complemento: Optional[str] = Field(None, max_length=150)
    cep: Optional[str] = None
    dpo_nome: Optional[str] = Field(None, max_length=255)
    dpo_email: Optional[EmailStr] = Field(None, max_length=255)

    model_config = {
        "str_strip_whitespace": True,
        "extra": "forbid",
    }

    @model_validator(mode="before")
    @classmethod
    def achatar_endereco(cls, dados):
        """Achata `endereco` (formato do to_dict(), enviado pelo front) nos
        campos planos do schema, para o `extra: forbid` não rejeitar a chave."""
        if isinstance(dados, dict) and isinstance(dados.get("endereco"), dict):
            dados = {**dados}
            endereco = dados.pop("endereco")
            for campo in ("cep", "bairro", "numero", "complemento"):
                if campo in endereco and campo not in dados:
                    dados[campo] = endereco[campo]
        return dados

    @field_validator("cnes")
    @classmethod
    def valida_cnes(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_cnes(v)

    @field_validator("dpo_nome", "dpo_email", mode="before")
    @classmethod
    def dpo_vazio_vira_none(cls, v):
        """"" ou só espaços viram None (EmailStr rejeitaria ""). O service lê
        None EXPLÍCITO nesses campos como "voltar ao padrão" (nome e e-mail do
        admin fundador): o DPO nunca fica nulo."""
        return _vazio_para_none(v)

    @field_validator("cep")
    @classmethod
    def valida_cep(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_cep(v)

    @field_validator("numero")
    @classmethod
    def valida_numero(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_numero(v)