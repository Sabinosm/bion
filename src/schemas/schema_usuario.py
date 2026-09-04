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
    tipo_usuario: Literal["medico", "enfermeiro", "admin"]
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
        tipo = self.tipo_usuario

        if tipo == "medico":
            if not self.numero_crm or not self.uf_crm:
                raise ValueError("Médicos precisam preencher 'numero-crm' e 'uf-crm'.")
            if self.senha:
                raise ValueError(
                    "Médicos não devem informar 'senha' no cadastro; o acesso "
                    "é definido em um fluxo de ativação de conta separado."
                )

        elif tipo == "enfermeiro":
            if not self.numero_coren or not self.uf_coren or not self.especialidade:
                raise ValueError(
                    "Enfermeiros precisam preencher 'numero-coren', 'uf-coren' e 'especialidade'."
                )
            if self.senha:
                raise ValueError(
                    "Enfermeiros não devem informar 'senha' no cadastro; o acesso "
                    "é definido em um fluxo de ativação de conta separado."
                )

        elif tipo == "admin":
            # ALTERADO: este schema não sabe se este "admin" é o super
            # admin fundador (Empresa.cadastrar_com_admin -- precisa de
            # senha, é o único super admin da empresa) ou um admin comum
            # criado depois por esse super admin (senha proibida, vai
            # por fluxo de ativação separado, igual médico/enfermeiro).
            # Essa distinção só existe no service via o parâmetro
            # is_super_admin, que nunca vem do payload do cliente -- o
            # schema não tem esse contexto e não deve adivinhar.
            #
            # Por isso a senha fica OPCIONAL aqui para admin, sem
            # checagem de presença/ausência. A obrigatoriedade é
            # responsabilidade de UsuarioService.criar():
            #   - is_super_admin=True (fundador): exige schema.senha.
            #   - is_super_admin=False (admin comum, criado por um
            #     super admin já existente): exige schema.senha ausente.

            # Admin não deveria mandar campos de médico/enfermeiro — evita payload inconsistente
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
                    f"Usuário admin não deve informar: {', '.join(campos_indevidos)}."
                )

        return self


class ConflictoError(Exception):
    """CPF, e-mail ou login já cadastrados para outro usuário."""

    pass


class AtualizacaoUsuarioSchema(CadastroUsuarioSchema):
    """
    Mesmas regras de formato do cadastro (CPF válido, senha forte, etc.),
    mas nada é obrigatório — o cliente só envia o que quer alterar.

    Atenção: 'tipo_usuario' também vira opcional aqui. Isso significa que,
    se o payload de update não mandar 'tipo_usuario', o model_validator de
    'valida_campos_por_profissao' (herdado) vai rodar com tipo=None e não
    vai validar nada de CRM/COREN — o que é o comportamento certo para um
    update parcial que não mexe na profissão. Quando o service mescla com
    os dados atuais do usuário (ver EmpresaUsuarioService.atualizar), a
    validação cruzada completa é refeita com o tipo real.
    """

    nome_completo: Optional[str] = Field(None, min_length=3, max_length=150)
    cpf: Optional[str] = None
    email: Optional[EmailStr] = None
    user_login: Optional[str] = Field(None, min_length=3, max_length=30)
    tipo_usuario: Optional[Literal["medico", "enfermeiro", "admin"]] = None
    senha: Optional[str] = Field(None, min_length=8, max_length=128)

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

