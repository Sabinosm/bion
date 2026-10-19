"""
schema_config.py

Schema de validação do payload de configurações do usuário (aparência e
idioma). Garante que só entra no banco algo que o frontend sabe interpretar:
sem ele, um payload malformado (campo com nome errado, tipo errado, valor fora
do domínio permitido) seria salvo em silêncio e só viraria bug na hora de
renderizar a interface.

Os valores permitidos espelham as opções oferecidas pelo frontend
(settingsModal.html). Ajustar aqui sempre que o conjunto de configurações
padrão do serviço ganhar um campo novo ou as opções do frontend mudarem.
"""

from typing import Optional, List

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

# Valores de .theme-option[data-theme-option] em settingsModal.html.
TEMAS_PERMITIDOS = {
    "dark", "light",
    "blue", "blue-light",
    "burgundy", "burgundy-light",
    "teal", "teal-light",
}
TAMANHOS_FONTE_PERMITIDOS = {"pequeno", "medio", "grande"}

# Opções do <select id="f-idioma"> em settingsModal.html. O conjunto é fechado
# (e não um regex genérico) porque a UI só oferece estas duas: qualquer outro
# valor não teria como ter vindo do formulário legítimo.
IDIOMAS_PERMITIDOS = {"pt-BR", "en-US"}

# Tradução dos tipos de erro nativos do pydantic (que vêm em inglês) para
# mensagens em português. Erros dos validadores customizados já são em português.
MENSAGENS_ERRO_PYDANTIC = {
    "extra_forbidden": "campo não permitido.",
    "string_type": "deve ser um texto.",
    "list_type": "deve ser uma lista.",
    "dict_type": "deve ser um objeto.",
    "model_type": "deve ser um objeto.",
}


class DesignSchema(BaseModel):
    """Seção `design`: tema e tamanho da fonte. Campos desconhecidos são rejeitados."""

    model_config = ConfigDict(extra="forbid")

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


class PreferenciasSchema(BaseModel):
    """Seção `preferencias`: lista de idiomas, não vazia e só com valores permitidos."""

    model_config = ConfigDict(extra="forbid")

    linguagem: Optional[List[str]] = None

    @field_validator("linguagem")
    @classmethod
    def validar_linguagem(cls, v):
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("linguagem não pode ser uma lista vazia.")
        for item in v:
            if item not in IDIOMAS_PERMITIDOS:
                raise ValueError(
                    f"linguagem contém valor inválido: '{item}'. "
                    f"Valores aceitos: {sorted(IDIOMAS_PERMITIDOS)}."
                )
        return v


class ConfiguracoesSchema(BaseModel):
    """Schema raiz do payload `configuracoes` do PUT de configurações.

    Todos os campos são opcionais porque a atualização é parcial (o usuário
    pode mandar só `design`, só `preferencias` ou só um sub-campo de cada),
    mas o que for enviado precisa bater com o formato esperado. Seções
    desconhecidas na raiz (ex.: "designe") são rejeitadas.
    """

    model_config = ConfigDict(extra="forbid")

    design: Optional[DesignSchema] = None
    preferencias: Optional[PreferenciasSchema] = None


def validar_configuracoes(dados: dict) -> dict:
    """Valida o payload de configurações e devolve o dict normalizado.

    O resultado não traz chaves com valor None, para o merge não sobrescrever
    o que o usuário não quis mudar.

    Args:
        dados: conteúdo de `configuracoes` recebido do client.

    Returns:
        Dict apenas com os campos enviados e válidos.

    Raises:
        ValueError: com mensagem em português sobre o primeiro problema
            encontrado, pensada para ser repassada direto ao usuário.
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
        if primeiro_erro["type"] == "value_error":
            # Erro dos validadores customizados: o pydantic prefixa com
            # "Value error, ", removido para a mensagem ficar limpa.
            motivo = primeiro_erro["msg"].removeprefix("Value error, ")
        else:
            motivo = MENSAGENS_ERRO_PYDANTIC.get(primeiro_erro["type"], "valor inválido.")
        raise ValueError(
            f"Configuração inválida em '{campo}': {motivo} "
            "Tente novamente."
        ) from ex

    return validado.model_dump(exclude_none=True)
