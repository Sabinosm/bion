"""schema_execucao.py

Contrato de entrada para executar um protocolo: descreve o corpo enviado pelo
front (sobre qual input e com quais respostas), independente da família de
cálculo. O protocolo é identificado pela rota, não pelo corpo.
"""
from pydantic import BaseModel, Field, ValidationError

from src.core.erros_pydantic import erros_pydantic_por_campo
from src.core.exceptions import DadosInvalidosError


class SchemaExecucaoRequest(BaseModel):
    id_input: int = Field(gt=0)
    respostas: dict[str, str | float | int | bool | None] = Field(default_factory=dict)


def parse_execucao_request(payload) -> SchemaExecucaoRequest:
    """Valida o corpo da requisição de execução.

    Raises:
        DadosInvalidosError: com os erros por campo (`erros`), para o front pintar o input certo.
    """
    try:
        return SchemaExecucaoRequest.model_validate(payload or {})
    except ValidationError as ex:
        raise DadosInvalidosError("Corpo da requisição inválido.", erros=erros_pydantic_por_campo(ex)) from ex
