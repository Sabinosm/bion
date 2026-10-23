"""schema_usuario.py -- schemas Pydantic do recurso Usuario.

Define a validação de entrada de três operações: cadastro de usuário,
atualização parcial e troca de senha pelo próprio usuário. Todo usuário
deve ser administrador e/ou ter função clínica (médico ou enfermeiro),
duas condições independentes que podem coexistir. Cada função clínica
exige seus próprios dados de conselho profissional, e a senha só é aceita
no cadastro do administrador principal fundador; os demais recebem acesso
por um fluxo de ativação separado, decidido no service.

A atualização reaproveita as regras de formato do cadastro com todos os
campos opcionais. A regra "usuário final precisa ter admin ou função
clínica" depende do estado salvo no banco, então na atualização é checada
pelo service após mesclar o payload com os dados atuais. A troca de senha
não pede a senha atual, pois a prova de identidade já ocorre no step-up.
"""

import re
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from src.core import validacoes as vl
from src.core.erros_pydantic import erros_pydantic_por_campo  # noqa: F401 (reexportado)
# Reexportadas para quem ainda importa daqui; são as mesmas classes de BionException.
from src.core.exceptions import DadosInvalidosError, ConflictoError  # noqa: F401


REGEX_LOGIN = re.compile(r"^[a-zA-Z0-9._@-]{3,30}$")
REGEX_UF = re.compile(r"^[A-Z]{2}$")
REGEX_NOME = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-]+$")


class CadastroUsuarioSchema(BaseModel):
    """Payload de POST /usuarios (criação de conta)."""

    nome_completo: str = Field(..., min_length=3, max_length=150)
    cpf: str
    email: EmailStr
    user_login: str = Field(..., min_length=3, max_length=30)
    tipo_papel: Optional[Literal["medico", "enfermeiro"]] = None
    is_admin: bool = False
    telefone: Optional[str] = None
    senha: Optional[str] = Field(None, min_length=8, max_length=128)

    numero_crm: Optional[str] = Field(None, alias="numero-crm")
    uf_crm: Optional[str] = Field(None, alias="uf-crm")
    rqe: Optional[str] = None

    numero_coren: Optional[str] = Field(None, alias="numero-coren")
    uf_coren: Optional[str] = Field(None, alias="uf-coren")
    especialidade: Optional[str] = Field(None, max_length=100)

    model_config = {
        "populate_by_name": True,  # aceita 'numero_crm' e o alias 'numero-crm'
        "str_strip_whitespace": True,
        "extra": "forbid",
    }

    # -- Validadores de campo (tolerantes a None para servir à atualização) --

    @field_validator("nome_completo")
    @classmethod
    def valida_nome_completo(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        partes = v.split()
        if len(partes) < 2:
            raise ValueError("Informe nome e sobrenome.")
        if not all(REGEX_NOME.match(p) for p in partes):
            raise ValueError("Nome completo contém caracteres inválidos.")
        return v

    @field_validator("cpf")
    @classmethod
    def valida_e_limpa_cpf(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not vl.validar_cpf(v):
            raise ValueError("O CPF está incorreto.")
        return re.sub(r"\D", "", v)

    @field_validator("email")
    @classmethod
    def normaliza_email(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if v else v

    @field_validator("user_login")
    @classmethod
    def valida_login(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not REGEX_LOGIN.match(v):
            raise ValueError(
                "Login deve ter 3-30 caracteres e conter apenas letras, "
                "números, ponto, hífen, underline ou @."
            )
        return v.lower()

    @field_validator("telefone")
    @classmethod
    def checar_telefone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not vl.validar_telefone_br(v):
            raise ValueError("Telefone com formato inválido.")
        return re.sub(r"\D", "", v)

    @field_validator("uf_crm", "uf_coren")
    @classmethod
    def valida_uf(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if not REGEX_UF.match(v):
            raise ValueError("UF deve conter exatamente 2 letras.")
        return v

    @field_validator("numero_crm", "numero_coren")
    @classmethod
    def valida_numero_registro(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.isdigit():
            raise ValueError("Número do registro deve conter apenas dígitos.")
        return v

    @field_validator("especialidade")
    @classmethod
    def valida_especialidade(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Especialidade inválida.")
        return v

    @field_validator("senha")
    @classmethod
    def valida_forca_senha(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        senha_valida, resposta = vl.validar_senha(v)
        if senha_valida:
            return v
        raise ValueError(resposta["erro"])

    # -- Validação cruzada entre campos --------------------------------------

    def _valida_dados_profissionais(self):
        """Confere os dados de conselho exigidos (ou proibidos) para o
        tipo_papel e a regra de senha de médicos/enfermeiros."""
        if self.tipo_papel == "medico":
            if not self.numero_crm or not self.uf_crm:
                raise ValueError("Médicos precisam preencher 'numero-crm' e 'uf-crm'.")
            if self.senha and not self.is_admin:
                raise ValueError(
                    "Médicos não devem informar 'senha' no cadastro; o acesso "
                    "é definido em um fluxo de ativação de conta separado."
                )

        elif self.tipo_papel == "enfermeiro":
            if not self.numero_coren or not self.uf_coren or not self.especialidade:
                raise ValueError(
                    "Enfermeiros precisam preencher 'numero-coren', 'uf-coren' e 'especialidade'."
                )
            if self.senha and not self.is_admin:
                raise ValueError(
                    "Enfermeiros não devem informar 'senha' no cadastro; o acesso "
                    "é definido em um fluxo de ativação de conta separado."
                )

        else:
            campos_indevidos = [
                nome
                for nome, valor in [
                    ("numero-crm", self.numero_crm),
                    ("uf-crm", self.uf_crm),
                    ("numero-coren", self.numero_coren),
                    ("uf-coren", self.uf_coren),
                    ("especialidade", self.especialidade),
                ]
                if valor
            ]
            if campos_indevidos:
                raise ValueError(
                    f"Sem 'tipo_papel' definido, não deve informar: {', '.join(campos_indevidos)}."
                )

    @model_validator(mode="after")
    def valida_campos_por_profissao(self):
        """tipo_papel e is_admin são independentes (admin que também
        atende). Todo usuário precisa de pelo menos um dos dois, para não
        existir conta sem regra de autorização aplicável. A regra de senha
        por tipo de admin (só o fundador define senha) fica no service."""
        self._valida_dados_profissionais()

        if not self.is_admin and self.tipo_papel is None:
            raise ValueError(
                "Usuário sem 'is_admin' precisa ter 'tipo_papel' definido "
                "('medico' ou 'enfermeiro') — todo usuário precisa ser "
                "administrador ou ter uma função clínica."
            )
        return self


class AtualizacaoUsuarioSchema(CadastroUsuarioSchema):
    """Payload de PUT /usuarios/<uuid>: update parcial, nada é obrigatório.

    is_admin é Optional[bool] = None (no cadastro o default é False): None
    significa "não veio, não mexer". Na prática o service rejeita qualquer
    mudança de is_admin por edição de cadastro.

    As regras que dependem do estado atual (função clínica, dados de
    conselho, "precisa ter admin ou função clínica") não são checadas
    aqui: o payload parcial não as tem por inteiro (ex.: dá para mudar só
    o CRM sem enviar tipo_papel). O service as valida depois, ao mesclar o
    payload com os dados salvos e revalidar como cadastro completo. Os
    validadores de formato dos campos são herdados do cadastro.
    """

    nome_completo: Optional[str] = Field(None, min_length=3, max_length=150)
    cpf: Optional[str] = None
    email: Optional[EmailStr] = None
    user_login: Optional[str] = Field(None, min_length=3, max_length=30)
    tipo_papel: Optional[Literal["medico", "enfermeiro"]] = None
    is_admin: Optional[bool] = None
    senha: Optional[str] = Field(None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def valida_campos_por_profissao(self):
        return self


class AlterarSenhaSchema(BaseModel):
    """Payload de PUT /usuarios/senha: troca de senha pelo próprio usuário.

    Sem `senha_atual`: a prova de identidade deveria ocorrer no step-up
    antes do endpoint (ver step_up.py).
    """

    senha_nova: str = Field(..., min_length=8, max_length=128)

    @field_validator("senha_nova")
    @classmethod
    def valida_forca_senha(cls, v: str) -> str:
        senha_valida, resposta = vl.validar_senha(v)
        if senha_valida:
            return v
        raise ValueError(resposta["erro"])