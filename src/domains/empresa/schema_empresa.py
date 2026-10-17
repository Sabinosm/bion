"""
Schema Pydantic de ENTRADA para Empresa (cadastro e atualização).

AtualizacaoEmpresaSchema divide os campos por sensibilidade:

- AUTOGERENCIÁVEIS: a própria empresa (via seu admin) pode alterar
  livremente. Dado cadastral comum, sem implicação legal ou financeira.

- RESTRITOS: hoje NINGUÉM pode alterar via este schema, porque o Bion
  ainda não tem um papel de "admin Bion" separado do "admin cliente".
  Quando esse papel existir, estes campos devem migrar para um
  schema/rota própria, acessível só por esse papel superior -- nunca
  pelo admin da empresa dona do dado, já que são campos que a própria
  empresa não deveria conseguir se autoconceder (ex: reativar o
  próprio plano suspenso).
"""

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ValidationError
from src.core import validacoes as vl
from src.core.erros_pydantic import erros_pydantic_por_campo


REGEX_CEP_LIMPO = re.compile(r"^\d{8}$")
REGEX_NUMERO_ENDERECO = re.compile(r"^[A-Za-z0-9°ºª\s\-/.,]{1,20}$")


class CadastroEmpresaSchema(BaseModel):
    """Usado na criação: campos obrigatórios permanecem obrigatórios."""

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
        if v is None or v == "":
            return None
        v = re.sub(r"\D", "", v)
        if len(v) != 7:
            raise ValueError("CNES deve conter 7 dígitos.")
        return v

    @field_validator("cep")
    @classmethod
    def valida_cep(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not vl.validar_cep(v):
            raise ValueError("CEP inválido.")
        return re.sub(r"\D", "", v)

    @field_validator("status_plano")
    @classmethod
    def valida_status_plano(cls, v: str) -> str:
        permitidos = {"ativo", "inativo", "suspenso", "cancelado"}
        if v not in permitidos:
            raise ValueError(f"status_plano deve ser um de: {', '.join(sorted(permitidos))}.")
        return v

    @model_validator(mode="after")
    def exige_cnpj_ou_cnes(self):
        if not self.cnpj and not self.cnes:
            raise ValueError("Informe o CNPJ ou o CNES.")
        return self


class AtualizacaoEmpresaSchema(BaseModel):
    """Atualização parcial de Empresa -- ver docstring do módulo para a
    divisão entre campos autogerenciáveis e restritos."""

    # -- Autogerenciáveis pelo admin da própria empresa ----------------
    nome_fantasia: Optional[str] = Field(None, min_length=2, max_length=255)
    numero: Optional[str] = Field(None, max_length=10)
    bairro: Optional[str] = Field(None, max_length=100)
    complemento: Optional[str] = Field(None, max_length=150)
    cep: Optional[str] = None
    dpo_nome: Optional[str] = Field(None, max_length=255)
    dpo_email: Optional[EmailStr] = Field(None, max_length=255)

    model_config = {
        "str_strip_whitespace": True,
        "extra": "forbid",  # qualquer campo restrito enviado já quebra aqui
    }

    @field_validator("cep")
    @classmethod
    def valida_cep(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not vl.validar_cep(v):
            raise ValueError("CEP inválido.")
        return re.sub(r"\D", "", v)

    @field_validator("nome_fantasia")
    @classmethod
    def valida_nome_fantasia(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Nome fantasia muito curto.")
        return v

    @field_validator("numero")
    @classmethod
    def valida_numero(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        if not REGEX_NUMERO_ENDERECO.match(v):
            raise ValueError("Número do endereço contém caracteres inválidos.")
        return v