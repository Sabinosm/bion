"""
Schema Pydantic de ENTRADA para Paciente: atualização (pessoal e
clínico) e criação.

PacienteAtualizarPessoalSchema / PacienteAtualizarClinicoSchema
refletem a mesma separação de PacienteService.atualizar_pessoal /
atualizar_clinico e são schemas de ATUALIZAÇÃO PARCIAL (tipo PATCH):
todo campo é opcional -- só o que vier no payload é validado e
aplicado.

PacienteCriarSchema é o schema de CRIAÇÃO (POST): os campos
obrigatórios no domínio (sexo_biologico, data_nascimento,
nome_completo, cpf) são de fato obrigatórios aqui -- ausência é erro,
diferente dos schemas de atualização acima.

O Literal de `status` é cópia manual do db.Enum de Paciente -- não há
introspecção automática do schema do banco aqui. Se o Enum do model
mudar, este arquivo precisa ser atualizado junto.

telefone/contato_emergencia_telefone usam validar_telefone_br (DDD
real, dígito 9 no celular, rejeita sequência repetida). cep usa
validar_e_devolver_cep (8 dígitos de verdade, rejeita sequência tipo
"11111111") e é normalizado para só-dígitos. rg, numero_residencia,
contato_emergencia_nome rejeitam string vazia/só-espaços. Datas
(data_obito, data_nascimento, data_primeiro_atendimento) não aceitam
valor futuro. cpf é validado com dígito verificador (validar_cpf).

_formatar_erros_pydantic e _strip_ou_none aparecem duplicadas abaixo
(uma vez para o bloco de atualização, outra para o de criação) de
propósito: um import cruzado entre os dois blocos criaria acoplamento
desnecessário para funções de poucas linhas. Se crescerem, viram um
util compartilhado em src.core.

id_regiao_geografica NÃO existe como campo em PacienteCriarSchema:
região é DERIVADA do cep (via CepService.regiao_por_cep) no service,
nunca aceita como valor cru do cliente -- ver PacienteService.cadastrar().
Se vier no payload bruto antes de chegar neste schema, deve ser
descartado/ignorado pelo controller/service. bairro também é
preenchido a partir da resolução de CEP quando ausente, mas tem
prioridade quando informado explicitamente.

status/falecido/data_obito propositalmente NÃO entram em
PacienteCriarSchema: são campos clínicos, e a única via de entrada
para eles é atualizar_clinico -- cadastro sempre cria com o default do
model (status="ativo", falecido=False).
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
        msg = erro["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        partes.append(f"{campo}: {msg}")
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
    """PATCH parcial. status é Literal (valor fora do Enum é rejeitado
    aqui, não vira IntegrityError cru no commit()).

    Regra de consistência: falecido=True FORÇA status="obito"
    automaticamente -- não é uma via de mão dupla. Não é exigido
    data_obito nem o inverso (status="obito" não obriga falecido=True
    nem data_obito); só a direção falecido->status é garantida.
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


class PacienteCriarSchema(BaseModel):
    """Schema de CRIAÇÃO -- campo ausente em obrigatório é erro,
    diferente dos schemas PATCH acima.

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