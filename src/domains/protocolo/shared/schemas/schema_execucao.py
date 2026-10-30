"""schema_execucao.py

Contrato de entrada para executar um protocolo: descreve o corpo enviado pelo
front (sobre qual input e com quais respostas), independente da família de
cálculo. O protocolo é identificado pela rota, não pelo corpo.
"""
from pydantic import BaseModel, Field, ValidationError

from src.core.exceptions import DadosInvalidosError


class SchemaExecucaoRequest(BaseModel):
    id_input: int = Field(gt=0)
    respostas: dict[str, str | float | int | bool | None] = Field(default_factory=dict)


def parse_execucao_request(payload) -> SchemaExecucaoRequest:
    """Valida o corpo da requisição de execução.

    Raises:
        DadosInvalidosError: com todos os problemas encontrados no corpo.
    """
    try:
        return SchemaExecucaoRequest.model_validate(payload or {})
    except ValidationError as ex:
        detalhes = "; ".join(
            f"{'.'.join(str(parte) for parte in erro['loc']) or 'corpo'}: {erro['msg']}"
            for erro in ex.errors()
        )
        raise DadosInvalidosError(f"Corpo da requisição inválido: {detalhes}") from ex
