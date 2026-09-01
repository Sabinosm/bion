"""
Schema Pydantic de ENTRADA para observação de tipo sanguíneo.

O Literal é cópia manual do db.Enum de ObservacaoTipoSanguineo -- não
há introspecção automática do schema do banco aqui. Se o Enum do
model mudar, este arquivo precisa ser atualizado junto.

Este era o único domínio clínico sem NENHUMA validação antes desta
mudança -- nem obrigatoriedade nem enum; um valor vazio ou fora do
Enum só falhava no commit(), como erro cru do banco.
"""

from typing import Literal

from pydantic import BaseModel, ValidationError


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


class TipoSanguineoCreateSchema(BaseModel):
    tipo_sanguineo: Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "desconhecido"]