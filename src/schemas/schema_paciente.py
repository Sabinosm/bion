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

from src.core.validacoes import validar_e_devolver_cep, validar_telefone_br, validar_cpf


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
    
    """
Schema Pydantic de ENTRADA para CRIAÇÃO de Paciente (POST), companion
de schema_paciente.py (que cobre só os PATCHes atualizar_pessoal /
atualizar_clinico).

Ao contrário dos schemas de atualização, este é um schema de CRIAÇÃO:
os campos marcados como obrigatórios no domínio (sexo_biologico,
data_nascimento, nome_completo, cpf) são de fato obrigatórios aqui --
ausência é erro, não "campo não veio, não mexe".

DECISÕES DE ESCOPO (confirmadas com o usuário):
- cpf: validado com validar_cpf() (dígito verificador), não só
  presença/tamanho -- "11111111111" ou "123" não passavam antes.
- telefone/contato_emergencia_telefone/cep: mesmo rigor do schema de
  atualização (validar_telefone_br / validar_e_devolver_cep).
- id_regiao_geografica SAI do schema de entrada como campo direto.
  Região passa a ser DERIVADA do cep (via CepService.regiao_por_cep)
  no service, nunca aceita como valor cru do cliente -- ver
  PacienteService.cadastrar(). Isso fecha uma inconsistência que
  existia antes (cliente podia mandar qualquer id_regiao_geografica,
  sem relação com o endereço real do paciente).
- bairro também passa a ser preenchido a partir da resolução de CEP
  (mesma chamada ao CepService), já que o model Paciente tem a coluna
  mas o cadastro antigo nunca a populava.

status/falecido/data_obito propositalmente NÃO entram aqui: são
campos clínicos, e a única via de entrada para eles é
atualizar_clinico (ver schema_paciente.py) -- cadastro sempre cria
com o default do model (status="ativo", falecido=False).
"""


def _formatar_erros_pydantic(exc: ValidationError) -> str:
    """Mesmo formato usado em schema_paciente.py -- mantido duplicado
    aqui de propósito (import cruzado entre os dois schemas criaria
    acoplamento desnecessário para uma função de 5 linhas); se algum
    dia isso crescer, vira um util compartilhado em src.core."""
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


class PacienteCriarSchema(BaseModel):
    """Schema de CRIAÇÃO -- campo ausente em obrigatório é erro,
    diferente dos schemas PATCH em schema_paciente.py.
 
    NOTA: id_regiao_geografica não existe como campo aqui de propósito
    -- ver docstring do módulo. Se vier no payload bruto (dict) antes
    de chegar neste schema, deve ser descartado/ignorado pelo
    controller/service, nunca repassado para o construtor de Paciente.
    """
 
    # ---- Obrigatórios (domínio Paciente + PacienteDadosPessoais) ----
    sexo_biologico: Literal["M", "F", "I"]
    data_nascimento: date
    nome_completo: str = Field(min_length=1, max_length=500)
    cpf: str
 
    # ---- Opcionais: Paciente ----
    data_primeiro_atendimento: Optional[date] = None
    tipo_sanguineo: Optional[str] = Field(default=None, max_length=10)
 
    # ---- Opcionais: PacienteDadosPessoais ----
    telefone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[EmailStr] = None
    logradouro: Optional[str] = Field(default=None, min_length=1, max_length=500)
    cep: Optional[str] = Field(default=None, max_length=9)
    numero_residencia: Optional[str] = Field(default=None, max_length=50)
    rg: Optional[str] = Field(default=None, max_length=100)
    contato_emergencia_nome: Optional[str] = Field(default=None, max_length=255)
    contato_emergencia_telefone: Optional[str] = Field(default=None, max_length=20)
 
    # ---- Opcionais: Paciente ----
    # Aceito via payload de propósito (ver docstring do módulo):
    # bairro do CEP (centróide/logradouro-base) pode divergir do
    # bairro real informado pelo paciente/UI. Quando informado, tem
    # prioridade sobre o valor resolvido automaticamente pelo
    # CepService -- só cai no automático se vier ausente.
    bairro: Optional[str] = Field(default=None, max_length=100)
 
    @field_validator("data_nascimento")
    @classmethod
    def _nascimento_nao_futuro(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("não pode ser uma data futura")
        return v
 
    @field_validator("data_primeiro_atendimento")
    @classmethod
    def _primeiro_atendimento_nao_futuro(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("não pode ser uma data futura")
        return v
 
    @field_validator("nome_completo", "logradouro")
    @classmethod
    def _nao_pode_ser_so_espacos(cls, v):
        if v is not None and not v.strip():
            raise ValueError("não pode ser vazio ou só espaços")
        return v
 
    @field_validator("rg", "numero_residencia", "contato_emergencia_nome", "bairro")
    @classmethod
    def _normalizado(cls, v):
        return _strip_ou_none(v)
 
    @field_validator("cpf")
    @classmethod
    def _cpf_valido(cls, v: str) -> str:
        if not validar_cpf(v):
            raise ValueError("CPF inválido")
        return v
 
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