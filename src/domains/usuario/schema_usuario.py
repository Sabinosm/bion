"""
Schemas Pydantic para o recurso Usuario (cadastro, atualização e troca de senha).

Contém:
- CadastroUsuarioSchema: payload de criação de usuário. Todo usuário deve
  ser administrador (is_admin=True) e/ou ter uma função clínica
  (tipo_papel="medico" | "enfermeiro"); as duas coisas são independentes
  e podem coexistir (ex.: admin que também atende clinicamente).
  Médicos exigem numero-crm/uf-crm; enfermeiros exigem numero-coren/
  uf-coren/especialidade. Senha só é aceita no cadastro para o super
  admin fundador — médicos e enfermeiros comuns recebem acesso por um
  fluxo de ativação separado (ver UsuarioService).
- AtualizacaoUsuarioSchema: mesma validação de formato do cadastro, mas
  com todos os campos opcionais (update parcial). is_admin usa
  Optional[bool] com None = "não alterar" e False = "remover admin
  explicitamente". A invariante "usuário final precisa ter admin ou
  papel clínico" não é checada aqui porque depende do estado atual do
  usuário no banco — isso é responsabilidade do service, após mesclar
  o payload com os dados existentes.
- AlterarSenhaSchema: payload de troca de senha por autoatendimento.
  Não tem campo de senha atual porque a prova de identidade já ocorre
  no step-up (WebAuthn ou senha+Google) antes do endpoint ser chamado.

Exceções de domínio: DadosInvalidosError, ConflictoError.
"""

import re
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ValidationError
from src.core import validacoes as vl


class DadosInvalidosError(Exception):
    """Erro de validação de dados de entrada (camada de negócio)."""

    pass


def _formatar_erros_pydantic(exc: ValidationError) -> str:
    """Converte os erros do Pydantic em uma mensagem curta, uma linha por
    campo (ex.: 'Campos obrigatórios ausentes: x, y')."""
    partes = []
    for erro in exc.errors():
        campo = ".".join(str(p) for p in erro["loc"]) or "(corpo)"
        partes.append(f"{campo}: {erro['msg']}")
    return "; ".join(partes)


# Regras de formato reaproveitáveis
REGEX_LOGIN = re.compile(r"^[a-zA-Z0-9._-]{3,30}$")
REGEX_UF = re.compile(r"^[A-Z]{2}$")


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

    # Campos específicos opcionais no payload geral
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

    # -- Validadores de campo individuais -----------------------------------

    @field_validator("nome_completo")
    @classmethod
    def valida_nome_completo(cls, v: str) -> str:
        partes = v.split()
        if len(partes) < 2:
            raise ValueError("Informe nome e sobrenome.")
        if not all(re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-]+$", p) for p in partes):
            raise ValueError("Nome completo contém caracteres inválidos.")
        return v

    @field_validator("cpf")
    @classmethod
    def valida_e_limpa_cpf(cls, v: str) -> str:
        if not vl.validar_cpf(v):
            raise ValueError("O CPF está incorreto.")
        return re.sub(r"\D", "", v)

    @field_validator("email")
    @classmethod
    def normaliza_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("user_login")
    @classmethod
    def valida_login(cls, v: str) -> str:
        if not REGEX_LOGIN.match(v):
            raise ValueError(
                "Login deve ter 3-30 caracteres e conter apenas letras, "
                "números, ponto, hífen ou underline."
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
        """Reaproveita vl.validar_senha (mesma função usada na atualização)."""
        if v is None:
            return None
        senha_valida, resposta = vl.validar_senha(v)
        if senha_valida:
            return v
        raise ValueError(resposta["erro"])

    # -- Validação cruzada entre campos --------------------------------------

    @model_validator(mode="after")
    def valida_campos_por_profissao(self):
        """
        tipo_papel e is_admin são checagens independentes (podem ambos ser
        verdadeiros: admin que também atende clinicamente). Todo usuário
        precisa ser admin ou ter um papel clínico definido — nunca nenhum
        dos dois, pra evitar conta "fantasma" sem regra de autorização
        aplicável. A obrigatoriedade/proibição de senha por tipo de conta
        (só o super admin fundador pode ter senha no cadastro) é resolvida
        no service via is_super_admin, não aqui.
        """
        if self.tipo_papel == "medico":
            if not self.numero_crm or not self.uf_crm:
                raise ValueError("Médicos precisam preencher 'numero-crm' e 'uf-crm'.")
            # Exceção: admin fundador que também é médico já recebe senha no cadastro.
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
            # Sem profissão clínica: não deve vir com campos de médico/enfermeiro.
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

        if not self.is_admin and self.tipo_papel is None:
            raise ValueError(
                "Usuário sem 'is_admin' precisa ter 'tipo_papel' definido "
                "('medico' ou 'enfermeiro') — todo usuário precisa ser "
                "administrador ou ter uma função clínica."
            )

        return self


class ConflictoError(Exception):
    """CPF, e-mail ou login já cadastrados para outro usuário."""

    pass


class AtualizacaoUsuarioSchema(CadastroUsuarioSchema):
    """
    Payload de update parcial: mesmas regras de formato do cadastro, mas
    nada é obrigatório — o cliente só envia o que quer alterar.

    is_admin é Optional[bool] = None aqui (diferente do default False no
    cadastro): None significa "não veio no payload, não mexer"; False
    significa "remover admin explicitamente". O service precisa
    distinguir os dois casos ao mesclar com os dados atuais.

    A invariante "usuário precisa ter admin ou papel clínico" (herdada
    do cadastro) é sobrescrita abaixo: num update parcial, ausência dos
    dois campos é o caso comum (payload não mexe neles) e não deve
    disparar erro — essa checagem só faz sentido após o service mesclar
    o payload com o estado atual do usuário no banco.
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
        """Mesma lógica de CRM/COREN/campos-indevidos do cadastro, mas sem a
        checagem de "sem admin e sem papel" — inaplicável a update parcial."""
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

        # A checagem de "usuário final sem admin e sem papel" precisa do
        # estado atual do banco mesclado ao payload — feita no service.
        return self

    @field_validator("cpf")
    @classmethod
    def valida_e_limpa_cpf(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not vl.validar_cpf(v):
            raise ValueError("O CPF está incorreto.")
        return re.sub(r"\D", "", v)

    @field_validator("user_login")
    @classmethod
    def valida_login(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not REGEX_LOGIN.match(v):
            raise ValueError(
                "Login deve ter 3-30 caracteres e conter apenas letras, "
                "números, ponto, hífen ou underline."
            )
        return v.lower()

    @field_validator("senha")
    @classmethod
    def valida_forca_senha(cls, v: Optional[str]) -> Optional[str]:
        senha_valida, resposta = vl.validar_senha(v)
        if senha_valida:
            return v
        raise ValueError(resposta["erro"])

    @field_validator("nome_completo")
    @classmethod
    def valida_nome_completo(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        partes = v.split()
        if len(partes) < 2:
            raise ValueError("Informe nome e sobrenome.")
        if not all(re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-]+$", p) for p in partes):
            raise ValueError("Nome completo contém caracteres inválidos.")
        return v


class AlterarSenhaSchema(BaseModel):
    """
    Payload de PUT /usuarios/senha — troca de senha pelo próprio usuário
    autenticado (ver UsuarioService.alterar_senha).

    Sem campo `senha_atual`: a prova de identidade já ocorre no step-up
    (WebAuthn, ou senha+Google com prompt=login) antes deste endpoint ser
    chamado, então pedir a senha atual de novo duplicaria uma prova sem
    ganho de segurança (ver step_up.py).
    """

    senha_nova: str = Field(..., min_length=8, max_length=128)

    @field_validator("senha_nova")
    @classmethod
    def valida_forca_senha(cls, v: str) -> str:
        senha_valida, resposta = vl.validar_senha(v)
        if senha_valida:
            return v
        raise ValueError(resposta["erro"])