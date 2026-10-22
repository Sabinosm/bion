"""Schema Pydantic do corpo de entrada da conduta de enfermagem.

O corpo traz só o que o profissional informa: a descrição e, opcionalmente, o UUID
do protocolo do catálogo que motivou a conduta. Autor, função, atendimento e data
vêm da sessão e do path, nunca do corpo (extra="forbid" recusa qualquer outro campo).
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

DESCRICAO_MIN = 3
DESCRICAO_MAX = 2000


class CondutaEnfermagemCriarSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    descricao_conduta: str = Field(min_length=DESCRICAO_MIN, max_length=DESCRICAO_MAX)
    uuid_protocolo_catalogo: Optional[str] = Field(default=None, min_length=36, max_length=36)
