import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from src.models.corp.empresa import Empresa
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
 
 

    """
Schema de atualização de Empresa.

Divisão de campos por sensibilidade:

- AUTOGERENCIÁVEIS: a própria empresa (via seu admin) pode alterar livremente.
  Dado cadastral comum, sem implicação legal ou financeira.

- RESTRITOS: hoje NINGUÉM pode alterar via este schema, porque o Bion ainda
  não tem um papel de "admin Bion" separado do "admin cliente". Quando esse
  papel existir, estes campos devem migrar para um schema/rota própria,
  acessível só por esse papel superior — nunca pelo admin da empresa dona
  do dado, já que são campos que a própria empresa não deveria conseguir
  se autoconceder (ex: reativar o próprio plano suspenso).

  - cnpj: identidade legal da empresa (Receita Federal). Trocar não é
    "atualizar cadastro", é virar outra pessoa jurídica mantendo o
    histórico antigo vinculado. Se houver erro de digitação real, deve
    ser corrigido manualmente (banco/suporte), nunca por PUT genérico.
  - razao_social: dado legal; menos crítico que CNPJ mas ainda exige
    auditoria de quem mudou, não autoatualização.
  - status_plano: controla se a empresa está ativa/suspensa/cancelada.
    Se o próprio cliente puder setar isso, ele pode se autoliberar de
    uma suspensão por inadimplência. Só deve ser alterado por sistema
    interno (webhook de pagamento) ou papel Bion.
  - plano: define cobrança/features contratadas; mesma lógica do acima.

- id_regiao_geografica: NÃO incluído por ora. Fica de fora até existir um
  processo de inserts manuais/curados das localidades do Brasil (conjunto
  finito, mas grande — não é algo pra aceitar como string livre vinda do
  cliente). Quando esse cadastro de regiões existir, este campo deve ser
  validado contra ele (FK existente), não recebido cru.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from src.core import validacoes as vl

REGEX_NUMERO_ENDERECO = re.compile(r"^[A-Za-z0-9°ºª\s\-/.,]{1,20}$")
class AtualizacaoEmpresaSchema(BaseModel):

    # -- Autogerenciáveis pelo admin da própria empresa ----------------
    nome_fantasia: Optional[str] = Field(None, min_length=2, max_length=150)
    numero: Optional[str] = Field(None, max_length=10)
    bairro: Optional[str] = Field(None, max_length=100)
    complemento: Optional[str] = Field(None, max_length=150)
    cep: Optional[str] = None

    # -- Restritos: bloqueados por enquanto (ver docstring acima) -------
    # Não declarados no schema. Se vierem no payload, "extra": "forbid"
    # abaixo já rejeita automaticamente:
    #   cnpj: ...
    #   razao_social: ...
    #   status_plano: ...
    #   plano: ...
    #   id_regiao_geografica: ...  # aguardando cadastro curado de regiões

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
        import re
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