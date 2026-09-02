"""
Schema Pydantic de ENTRADA para observação de tipo sanguíneo.

O Literal é cópia manual do db.Enum de ObservacaoTipoSanguineo -- não
há introspecção automática do schema do banco aqui. Se o Enum do
model mudar, este arquivo precisa ser atualizado junto.

Este era o único domínio clínico sem NENHUMA validação antes desta
mudança -- nem obrigatoriedade nem enum; um valor vazio ou fora do
Enum só falhava no commit(), como erro cru do banco.

ALTERADO: normalização de caixa antes de validar contra o Literal --
"a+", "A+" e " A+ " agora são todos aceitos e normalizados para "A+".
Antes, só a grafia exata do Enum passava e qualquer variação de caixa
(bem provável vindo de input de formulário/mobile) caía como erro de
formato em vez de ser normalizada.
"""

from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

_TIPOS_VALIDOS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "DESCONHECIDO"}
# "desconhecido" é o único valor do Enum que não é sigla de tipo
# sanguíneo -- mapeado à parte para manter a grafia minúscula original
# depois de normalizar a entrada.
_MAPA_NORMALIZACAO = {v: v for v in _TIPOS_VALIDOS if v != "DESCONHECIDO"}
_MAPA_NORMALIZACAO["DESCONHECIDO"] = "desconhecido"


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

    @field_validator("tipo_sanguineo", mode="before")
    @classmethod
    def _normalizar_caixa(cls, v):
        if isinstance(v, str):
            chave = v.strip().upper()
            if chave in _MAPA_NORMALIZACAO:
                return _MAPA_NORMALIZACAO[chave]
        return v