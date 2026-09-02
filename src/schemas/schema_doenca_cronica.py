"""
Schema Pydantic de ENTRADA para doença crônica.

O Literal de `status` é cópia manual do db.Enum de DoencaCronica --
não há introspecção automática do schema do banco aqui. Se o Enum do
model mudar, este arquivo precisa ser atualizado junto.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError


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


class DoencaCronicaCreateSchema(BaseModel):
    codigo_cid10: str = Field(min_length=1, max_length=10)
    descricao_cid10: str = Field(min_length=1, max_length=255)
    desde: date
    status: Literal["ativa", "em-remissao"]
    observacoes: Optional[str] = None


class DoencaCronicaAtualizarSchema(BaseModel):
    """NOVO: atualização parcial (PATCH-like) -- todo campo é opcional,
    só o que vier é validado e aplicado. codigo_cid10/descricao_cid10
    incluídos como editáveis: diferente de tipo sanguíneo (que separa
    'novo exame' de 'corrigir'), doença crônica não tem um conceito de
    'nova ocorrência' -- é o mesmo registro sendo corrigido/atualizado
    (ex: mudar status de 'ativa' para 'em-remissao' com o tempo, ou
    corrigir um CID digitado errado).
    """
    codigo_cid10: Optional[str] = Field(default=None, min_length=1, max_length=10)
    descricao_cid10: Optional[str] = Field(default=None, min_length=1, max_length=255)
    desde: Optional[date] = None
    status: Optional[Literal["ativa", "em-remissao"]] = None
    observacoes: Optional[str] = None

    def campos_informados(self) -> dict:
        return self.model_dump(exclude_unset=True)