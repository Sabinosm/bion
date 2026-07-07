import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from src.database.corp import Empresa
from src.core import validacoes as vl


class DadosInvalidosError(Exception):
    pass
 
 
class ConflictoError(Exception):
    pass
 
 
REGEX_CEP_LIMPO = re.compile(r"^\d{8}$")
 
 
class CadastroEmpresaSchema(BaseModel):
    """Usado na criação: campos obrigatórios permanecem obrigatórios."""
 
    nome_fantasia: str = Field(..., min_length=2, max_length=150)
    razao_social: Optional[str] = Field(None, max_length=150)
    cnpj: str
    numero: Optional[str] = Field(None, max_length=10)
    bairro: Optional[str] = Field(None, max_length=100)
    complemento: Optional[str] = Field(None, max_length=100)
    cep: Optional[str] = None
    id_regiao_geografica: Optional[int] = Field(None, gt=0)
    status_plano: str = "ativo"
    plano: Optional[str] = None
 
    model_config = {
        "str_strip_whitespace": True,
        "extra": "forbid",
    }
 
    @field_validator("cnpj")
    @classmethod
    def valida_e_limpa_cnpj(cls, v: str) -> str:
        if not vl.validar_cnpj(v):
            raise ValueError("O CNPJ está incorreto.")
        return re.sub(r"\D", "", v)
 
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
 
 
class AtualizacaoEmpresaSchema(CadastroEmpresaSchema):
    """
    Mesmas regras de formato do cadastro, mas nada é obrigatório:
    o usuário só manda os campos que quer alterar.
    Reaproveita os validators de CNPJ/CEP/status_plano automaticamente,
    pois Pydantic só roda o validator se o campo não for None.
    """
 
    nome_fantasia: Optional[str] = Field(None, min_length=2, max_length=150)
    cnpj: Optional[str] = None
    status_plano: Optional[str] = None
 
    @field_validator("cnpj")
    @classmethod
    def valida_e_limpa_cnpj(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not vl.validar_cnpj(v):
            raise ValueError("O CNPJ está incorreto.")
        return re.sub(r"\D", "", v)
 
    @field_validator("status_plano")
    @classmethod
    def valida_status_plano(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        permitidos = {"ativo", "inativo", "suspenso", "cancelado"}
        if v not in permitidos:
            raise ValueError(f"status_plano deve ser um de: {', '.join(sorted(permitidos))}.")
        return v