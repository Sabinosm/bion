"""Schema de validação para o payload de `configuracoes` do domínio
Configuracao.

Por quê isso existe:
`ConfiguracaoService.atualizar` fazia um merge raso (`dict.update`) de
qualquer JSON recebido, sem validar formato. Um payload malformado
(campo com nome errado, tipo errado, valor fora do domínio permitido)
era salvo silenciosamente e só se manifestava como bug depois, na hora
de renderizar a UI. Este schema garante que só entra no banco algo que
o frontend realmente sabe interpretar.

Ajustar aqui sempre que:
- `ConfiguracaoService.CONFIGURACOES_DEFAULT` ganhar um novo campo;
- os valores permitidos de tema / tamanho de fonte / idiomas mudarem
  no frontend (settingsModal.html).
"""

from typing import Optional, List

from pydantic import BaseModel, ValidationError, field_validator


# Ajustar estes conjuntos conforme as opções reais oferecidas no
# painel de Preferências (settingsModal.html / settings.js).
TEMAS_PERMITIDOS = {"light", "dark", "teal", "teal-light", "blue", "blue-light", "burgundy", "burgundy-light"}
TAMANHOS_FONTE_PERMITIDOS = {"pequeno", "medio", "grande"}

# Idiomas no formato IETF BCP 47 (pt-BR, en-US, es-ES, ...). Se a lista
# de idiomas suportados pela UI for fixa, troque por um `set` fechado
# igual aos dois acima e valide contra ele.
_ID_LINGUAGEM_PATTERN = r"^[a-z]{2}(-[A-Z]{2})?$"


class DesignSchema(BaseModel):
    tema: Optional[str] = None
    tamanho_fonte: Optional[str] = None

    @field_validator("tema")
    @classmethod
    def validar_tema(cls, v):
        if v is not None and v not in TEMAS_PERMITIDOS:
            raise ValueError(
                f"tema inválido: '{v}'. Valores aceitos: {sorted(TEMAS_PERMITIDOS)}."
            )
        return v

    @field_validator("tamanho_fonte")
    @classmethod
    def validar_tamanho_fonte(cls, v):
        if v is not None and v not in TAMANHOS_FONTE_PERMITIDOS:
            raise ValueError(
                f"tamanho_fonte inválido: '{v}'. "
                f"Valores aceitos: {sorted(TAMANHOS_FONTE_PERMITIDOS)}."
            )
        return v

    class Config:
        extra = "forbid"  # rejeita campos desconhecidos dentro de "design"


class PreferenciasSchema(BaseModel):
    linguagem: Optional[List[str]] = None

    @field_validator("linguagem")
    @classmethod
    def validar_linguagem(cls, v):
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("linguagem não pode ser uma lista vazia.")
        import re
        for item in v:
            if not isinstance(item, str) or not re.match(_ID_LINGUAGEM_PATTERN, item):
                raise ValueError(
                    f"linguagem contém valor inválido: '{item}'. "
                    "Esperado formato tipo 'pt-BR', 'en-US'."
                )
        return v

    class Config:
        extra = "forbid"


class ConfiguracoesSchema(BaseModel):
    """Schema raiz do payload `configuracoes` recebido em PUT /configuracao.

    Todos os campos são opcionais no schema porque `atualizar()` faz
    merge parcial (o usuário pode mandar só `design`, só `preferencias`,
    ou só um sub-campo de cada) -- mas o que for enviado precisa bater
    com o formato esperado.
    """

    design: Optional[DesignSchema] = None
    preferencias: Optional[PreferenciasSchema] = None

    class Config:
        extra = "forbid"  # rejeita seções desconhecidas na raiz (ex: "designe")


def validar_configuracoes(dados: dict) -> dict:
    """Valida o payload de configuracoes e retorna o dict já normalizado
    (sem chaves com valor None) pronto para o merge no service.

    Levanta `ValueError` com uma mensagem amigável em português no
    primeiro problema encontrado -- pensada para ser repassada direto
    ao usuário final via `BionException`/`json_error`.
    """
    if not isinstance(dados, dict):
        raise ValueError(
            "Formato inválido. Tente novamente enviando um objeto JSON "
            "com as configurações a atualizar."
        )

    try:
        validado = ConfiguracoesSchema(**dados)
    except ValidationError as ex:
        primeiro_erro = ex.errors()[0]
        campo = ".".join(str(p) for p in primeiro_erro["loc"])
        motivo = primeiro_erro["msg"]
        # pydantic prefixa erros de @field_validator com "Value error, ";
        # removemos para a mensagem ficar limpa para o usuário final.
        motivo = motivo.removeprefix("Value error, ")
        raise ValueError(
            f"Configuração inválida em '{campo}': {motivo} "
            "Tente novamente."
        ) from ex

    # model_dump remove campos não enviados (None) para não sobrescrever
    # à toa nada que o usuário não quis mudar.
    return validado.model_dump(exclude_none=True)