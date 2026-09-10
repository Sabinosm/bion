import json
import re
from typing import Optional, Tuple, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from src.core import validacoes as vl
from src.core.security import aes_encrypt, ph  # vl.validar_cpf, vl.validar_telefone_br, etc.

# ---------------------------------------------------------------------------
# Exceção de domínio
# ---------------------------------------------------------------------------


class DadosInvalidosError(Exception):
    """Erro de validação de dados de entrada (camada de negócio)."""

    pass


# ---------------------------------------------------------------------------
# Regras de formato reaproveitáveis
# ---------------------------------------------------------------------------

REGEX_LOGIN = re.compile(r"^[a-zA-Z0-9._-]{3,30}$")
REGEX_UF = re.compile(r"^[A-Z]{2}$")


class CadastroUsuarioSchema(BaseModel):

    nome_completo: str = Field(..., min_length=3, max_length=150)
    cpf: str
    email: EmailStr
    user_login: str = Field(..., min_length=3, max_length=30)
    # ALTERADO (assertivo, sem transição): tipo_usuario Literal único
    # SAIU. Duas dimensões ortogonais entram no lugar — reflete o
    # mesmo desenho já adotado em Usuario (is_admin + funcao_clinica).
    # Um usuário pode ter eh_admin=True e tipo_papel="medico" ao mesmo
    # tempo (admin que também atende clinicamente).
    tipo_papel: Optional[Literal["medico", "enfermeiro"]] = None
    eh_admin: bool = False
    telefone: Optional[str] = None

    # ALTERADO: era Optional[str] = Field(..., ...) -- Optional junto
    # com obrigatório (...) é contraditório. Senha agora é opcional
    # aqui no nível de campo; a obrigatoriedade real (só o super admin
    # fundador precisa, ninguém mais pode) é regra cruzada, resolvida
    # fora deste schema -- ver comentário no ramo "admin" abaixo.

    senha: Optional[str] = Field(None, min_length=8, max_length=128)

    # Campos específicos opcionais no payload geral
    numero_crm: Optional[str] = Field(None, alias="numero-crm")
    uf_crm: Optional[str] = Field(None, alias="uf-crm")
    rqe: Optional[str] = None

    numero_coren: Optional[str] = Field(None, alias="numero-coren")
    uf_coren: Optional[str] = Field(None, alias="uf-coren")
    especialidade: Optional[str] = Field(None, max_length=100)

    model_config = {
        "populate_by_name": True,  # aceita tanto 'numero_crm' quanto o alias 'numero-crm'
        "str_strip_whitespace": True,  # já faz .strip() em todo campo str automaticamente
        "extra": "forbid",  # rejeita chaves inesperadas no payload (mais seguro)
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
        # ALTERADO: essa checagem de força só existia em
        # AtualizacaoUsuarioSchema -- o cadastro validava só tamanho
        # (min_length=8), aceitando senha fraca desde que tivesse 8+
        # caracteres. Reaproveita vl.validar_senha, mesma função já
        # usada na atualização.

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
        ALTERADO (assertivo, sem transição): antes era um switch
        if/elif/elif mutuamente exclusivo por tipo_usuario. Agora são
        duas checagens INDEPENDENTES — tipo_papel e eh_admin podem
        ambos ser verdadeiros ao mesmo tempo (admin que também atende).

        Regra de senha continua ligada só a "é o super admin fundador",
        nunca a tipo_papel — isso já era assim antes e não muda.
        """
        if self.tipo_papel == "medico":
            if not self.numero_crm or not self.uf_crm:
                raise ValueError("Médicos precisam preencher 'numero-crm' e 'uf-crm'.")
            if self.senha:
                raise ValueError(
                    "Médicos não devem informar 'senha' no cadastro; o acesso "
                    "é definido em um fluxo de ativação de conta separado."
                )

        elif self.tipo_papel == "enfermeiro":
            if not self.numero_coren or not self.uf_coren or not self.especialidade:
                raise ValueError(
                    "Enfermeiros precisam preencher 'numero-coren', 'uf-coren' e 'especialidade'."
                )
            if self.senha:
                raise ValueError(
                    "Enfermeiros não devem informar 'senha' no cadastro; o acesso "
                    "é definido em um fluxo de ativação de conta separado."
                )

        else:
            # tipo_papel is None — sem profissão clínica associada.
            # Não deveria vir com campos de médico/enfermeiro preenchidos,
            # evita payload inconsistente (ex: eh_admin=True mandando
            # numero-crm sem tipo_papel="medico" para dar sentido a isso).
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

        # ADICIONADO: invariante que faltava na primeira versão desta
        # migração. eh_admin=False e tipo_papel=None ao mesmo tempo
        # criaria um usuário que não é admin nem tem profissão clínica
        # -- "fantasma" no sistema, sem se encaixar em nenhuma regra de
        # autorização (nem requer_admin, nem requer_papel_clinico
        # passam). A regra de negócio é: admin PODE ter papel clínico
        # (opcional), quem não é admin DEVE ter (obrigatório).
        if not self.eh_admin and self.tipo_papel is None:
            raise ValueError(
                "Usuário sem 'eh_admin' precisa ter 'tipo_papel' definido "
                "('medico' ou 'enfermeiro') — todo usuário precisa ser "
                "administrador ou ter uma função clínica."
            )

        # ALTERADO: a regra de senha para admin (obrigatória para o
        # super admin fundador, proibida para admin comum) permanece
        # responsabilidade de UsuarioService.criar() via is_super_admin
        # — o schema não tem esse contexto e não deve adivinhar. Isso
        # vale tanto para eh_admin=True com tipo_papel=None (admin puro)
        # quanto para eh_admin=True com tipo_papel setado (admin que
        # também atende). Nenhuma checagem de senha aqui para eh_admin
        # isoladamente — deliberado, ver service.py.

        return self


class ConflictoError(Exception):
    """CPF, e-mail ou login já cadastrados para outro usuário."""

    pass


class AtualizacaoUsuarioSchema(CadastroUsuarioSchema):
    """
    Mesmas regras de formato do cadastro (CPF válido, senha forte, etc.),
    mas nada é obrigatório — o cliente só envia o que quer alterar.

    Atenção: 'tipo_papel' também é opcional aqui. Isso significa que,
    se o payload de update não mandar 'tipo_papel', o model_validator de
    'valida_campos_por_profissao' (herdado) vai rodar com tipo_papel=None
    e não vai validar nada de CRM/COREN — o que é o comportamento certo
    para um update parcial que não mexe na profissão. Quando o service
    mescla com os dados atuais do usuário (ver EmpresaUsuarioService.
    atualizar), a validação cruzada completa é refeita com o tipo real.

    Atenção 2: 'eh_admin' aqui é Optional[bool] = None, DIFERENTE do
    default False em CadastroUsuarioSchema. None significa "não veio no
    payload, não mexer nesse campo" — False significa "remover admin
    explicitamente". O service precisa distinguir os dois casos ao
    mesclar com os dados atuais (não pode tratar None como False).

    Atenção 3: a invariante "não-admin precisa ter tipo_papel" (ver
    valida_campos_por_profissao no pai) É SOBRESCRITA aqui embaixo.
    No cadastro, ausência de ambos é sempre inválida. No update
    parcial, ausência de ambos é o caso comum (o payload não está
    mexendo em papel/admin, só em outro campo) — não pode disparar
    erro. A checagem "usuário final ficaria sem admin e sem papel"
    só faz sentido quando o service já mesclou com o estado atual do
    banco, não aqui no schema isolado.
    """

    nome_completo: Optional[str] = Field(None, min_length=3, max_length=150)
    cpf: Optional[str] = None
    email: Optional[EmailStr] = None
    user_login: Optional[str] = Field(None, min_length=3, max_length=30)
    # ALTERADO: tipo_usuario saiu. tipo_papel já é Optional por herança
    # (redeclarado aqui só por clareza); eh_admin também precisa ficar
    # Optional no update parcial — None significa "não mexer no campo",
    # diferente de False ("remover admin explicitamente"). O service
    # que mescla com os dados atuais (EmpresaUsuarioService.atualizar)
    # precisa distinguir esses dois casos.
    tipo_papel: Optional[Literal["medico", "enfermeiro"]] = None
    eh_admin: Optional[bool] = None
    senha: Optional[str] = Field(None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def valida_campos_por_profissao(self):
        """
        SOBRESCRITO do pai: reaproveita toda a lógica de
        CRM/COREN/campos-indevidos (mesmo corpo), mas SEM a checagem
        "not eh_admin and tipo_papel is None" -- essa invariante só
        faz sentido no cadastro completo. Num update parcial, os dois
        campos ausentes é o caso normal (payload não mexe neles).
        """
        if self.tipo_papel == "medico":
            if not self.numero_crm or not self.uf_crm:
                raise ValueError("Médicos precisam preencher 'numero-crm' e 'uf-crm'.")
            if self.senha:
                raise ValueError(
                    "Médicos não devem informar 'senha' no cadastro; o acesso "
                    "é definido em um fluxo de ativação de conta separado."
                )

        elif self.tipo_papel == "enfermeiro":
            if not self.numero_coren or not self.uf_coren or not self.especialidade:
                raise ValueError(
                    "Enfermeiros precisam preencher 'numero-coren', 'uf-coren' e 'especialidade'."
                )
            if self.senha:
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

        # DELIBERADAMENTE OMITIDO (diferente do pai): a checagem de
        # "usuário final sem admin e sem papel" precisa do estado atual
        # do banco mesclado com o payload -- só o service tem essa
        # visão. Ver EmpresaUsuarioService.atualizar / service_atualizar.py.

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
        if senha_valida == True:
            return v
        else:
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