
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
REGEX_SENHA_FORTE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{6,}$")  # letra + número, min 6
 
 
class CadastroUsuarioSchema(BaseModel):
 
    nome_completo: str = Field(..., min_length=3, max_length=150)
    cpf: str
    email: EmailStr
    user_login: str = Field(..., min_length=3, max_length=30)
    tipo_usuario: Literal["medico", "enfermeiro", "admin"]
    senha: str = Field(..., min_length=6, max_length=72)  # 72 = limite prático do bcrypt/argon2
    telefone: Optional[str] = None
 
    # Campos específicos opcionais no payload geral
    numero_crm: Optional[str] = Field(None, alias="numero-crm")
    uf_crm: Optional[str] = Field(None, alias="uf-crm")
    rqe: Optional[str] = None
 
    numero_coren: Optional[str] = Field(None, alias="numero-coren")
    uf_coren: Optional[str] = Field(None, alias="uf-coren")
    especialidade: Optional[str] = Field(None, max_length=100)
 
    model_config = {
        "populate_by_name": True,   # aceita tanto 'numero_crm' quanto o alias 'numero-crm'
        "str_strip_whitespace": True,  # já faz .strip() em todo campo str automaticamente
        "extra": "forbid",          # rejeita chaves inesperadas no payload (mais seguro)
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
 
    @field_validator("senha")
    @classmethod
    def valida_forca_senha(cls, v: str) -> str:
        if not REGEX_SENHA_FORTE.match(v):
            raise ValueError(
                "Senha deve ter ao menos 6 caracteres, incluindo letras e números."
            )
        return v
 
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
 
    # -- Validação cruzada entre campos --------------------------------------
 
    @model_validator(mode="after")
    def valida_campos_por_profissao(self):
        tipo = self.tipo_usuario
 
        if tipo == "medico":
            if not self.numero_crm or not self.uf_crm:
                raise ValueError("Médicos precisam preencher 'numero-crm' e 'uf-crm'.")
 
        elif tipo == "enfermeiro":
            if not self.numero_coren or not self.uf_coren or not self.especialidade:
                raise ValueError(
                    "Enfermeiros precisam preencher 'numero-coren', 'uf-coren' e 'especialidade'."
                )
 
        elif tipo == "admin":
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
    senha: Optional[str] = Field(None, min_length=6, max_length=72)
 
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
        if v is None:
            return None
        if not REGEX_SENHA_FORTE.match(v):
            raise ValueError(
                "Senha deve ter ao menos 6 caracteres, incluindo letras e números."
            )
        return v
 
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
 
 
# ---------------------------------------------------------------------------
# Camada de processamento de negócio
# ---------------------------------------------------------------------------
def validacao_input(self, dados: dict) -> Tuple[dict, Optional[str]]:
    try:
        schema = CadastroUsuarioSchema(**dados)
    except DadosInvalidosError:
        raise
    except Exception as e:
        # Pydantic ValidationError e afins — erro de dado do usuário
        raise DadosInvalidosError(f"Erro de validação: {e}") from e
 
    dados_tratados = {
        "nome_completo": schema.nome_completo,
        "cpf": aes_encrypt(schema.cpf),
        "cpf_hash": ph.hash(schema.cpf),
        "email": schema.email,
        "telefone": schema.telefone,
        "user_login": schema.user_login,
        "tipo_usuario": schema.tipo_usuario,
        "hash_senha": ph.hash(schema.senha),
    }
 
    atributos_dict = {}
    if schema.tipo_usuario == "medico":
        atributos_dict = {
            "numero-crm": schema.numero_crm,
            "uf-crm": schema.uf_crm,
            "rqe": (schema.rqe or "").strip(),
        }
    elif schema.tipo_usuario == "enfermeiro":
        atributos_dict = {
            "numero-coren": schema.numero_coren,
            "uf-coren": schema.uf_coren,
            "especialidade": schema.especialidade,
        }
 
    atributos_json = json.dumps(atributos_dict) if atributos_dict else None
 
    return dados_tratados, atributos_json
 
